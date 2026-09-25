import os
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from epgeneral_wheeltec_integration.readiness import Readiness


class ReadinessTests(unittest.TestCase):
    def check(self):
        obj = Readiness.__new__(Readiness)
        obj.received, obj.errors = {}, {}
        obj.rospy = SimpleNamespace(Time=SimpleNamespace(now=lambda: SimpleNamespace(to_sec=lambda: 100.0)))
        return obj

    def test_stale_or_future_messages_do_not_make_sensor_ready(self):
        check = self.check()
        for stamp in (0, 90, 101):
            check.callback(SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(to_sec=lambda: stamp))), '/livox/lidar')
            self.assertNotIn('/livox/lidar', check.received)
        check.callback(SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(to_sec=lambda: 99.9))), '/livox/lidar')
        self.assertIn('/livox/lidar', check.received)

    def test_invalid_voltage_does_not_make_chassis_ready(self):
        check = self.check()
        for voltage in (float('nan'), 0, -1):
            check.callback(SimpleNamespace(data=voltage), '/PowerVoltage')
            self.assertNotIn('/PowerVoltage', check.received)
        check.callback(SimpleNamespace(data=24.0), '/PowerVoltage')
        self.assertIn('/PowerVoltage', check.received)


@unittest.skipIf(os.name == 'nt', 'Linux process and Bash lifecycle tests')
class BashStartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.script = Path(os.environ.get('CCS_STARTUP_TEST_PATH', str(Path(__file__).resolve().parents[2] / 'profiles/wheeltec_r550p/start_ccs_edge_dev.sh')))
        self.env = dict(os.environ, CCS_EDGE_WORKSPACE=str(self.root), START_SCRIPT=str(self.script))

    def shell(self, code):
        return subprocess.run(['bash', '-c', 'source "$START_SCRIPT"; ' + code], env=self.env,
                              capture_output=True, text=True, timeout=15)

    def test_shutdown_without_owned_processes_never_touches_external_master(self):
        result = self.shell('master_exists() { echo UNEXPECTED; }; shutdown_all 0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('UNEXPECTED', result.stdout)

    def test_shutdown_orders_task_release_video_algorithms_drivers_master(self):
        result = self.shell('''PIDS=(101 102 103 104 105 106); ROSCORE_PID=107; VIDEO_OWNED=true
stop_process() { echo "stop:$1"; }
owned_process_alive() { return 0; }
master_exists() { return 0; }
release_control() { echo release; }
run_quiet() { echo "helper:$*"; }
shutdown_all 0''')
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0:2], ['stop:106','release'])
        self.assertIn('stopped --timeout 10', lines[2])
        self.assertIn('manage_ccs_video.sh stop', lines[3])
        self.assertEqual(lines[4:10], ['stop:105','stop:104','stop:103','stop:102','stop:101','stop:107'])

    def test_foreign_process_is_not_signaled(self):
        child = subprocess.Popen(['sleep','30'], start_new_session=True)
        try:
            result = self.shell('stop_process ' + str(child.pid))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('ownership changed', result.stdout)
            self.assertIsNone(child.poll())
        finally:
            child.terminate(); child.wait(timeout=3)

    def test_owned_child_receives_int_and_exits(self):
        child = self.root / 'child.py'
        child.write_text('import signal,time,sys\nsignal.signal(signal.SIGINT, lambda *a: sys.exit(0))\nopen(sys.argv[1],"w").close()\ntime.sleep(30)\n')
        result = self.shell('''setsid python3 "$WORKSPACE/child.py" "$WORKSPACE/ready" &
pid=$!
for attempt in $(seq 1 100); do [[ -e "$WORKSPACE/ready" ]] && break; sleep .02; done
owned_process_alive "$pid"
stop_process "$pid"
! process_alive "$pid"''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_duplicate_startup_lock_is_rejected_and_released(self):
        first = subprocess.Popen(['bash','-c','source "$START_SCRIPT"; acquire_startup_locks; touch "$WORKSPACE/ready"; exec sleep 30'],env=self.env)
        try:
            import time
            deadline=time.monotonic()+3
            while not (self.root/'ready').exists() and time.monotonic()<deadline: time.sleep(.02)
            self.assertTrue((self.root/'ready').exists())
            result=self.shell('acquire_startup_locks')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('legacy startup lock',result.stderr)
        finally:
            first.terminate();first.wait(timeout=3)
        self.assertEqual(self.shell('acquire_startup_locks').returncode,0)

    def test_video_failure_cleans_partial_start_and_does_not_abort_base(self):
        manager=self.root/'manage_ccs_video.sh'
        manager.write_text('#!/bin/bash\necho "$1" >>"'+str(self.root/'calls')+'"\n[[ "$1" == stop ]]\n')
        manager.chmod(0o755)
        result=self.shell('start_optional_video; [[ "$VIDEO_OWNED" == false ]]; echo BASE_CONTINUES')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('BASE_CONTINUES',result.stdout)
        self.assertEqual((self.root/'calls').read_text().splitlines(),['start','stop'])

    def test_mapping_stop_refuses_unrelated_live_pid(self):
        script = os.environ.get('CCS_MAPPING_TEST_PATH')
        if not script: self.skipTest('deployed mapping script path required')
        pidfile = self.root / 'mapping.pid'
        pidfile.write_text(str(os.getpid()) + '\n')
        Path(str(pidfile) + '.identity').write_text(Path('/proc/self/stat').read_text().split()[21])
        result = subprocess.run(['bash', script, '--stop', str(pidfile), '1'],
            env=dict(self.env, CCS_ALGORITHM_LOCK_FILE=str(self.root/'lock')),capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('not owned',result.stderr)


if __name__ == '__main__':
    unittest.main()
