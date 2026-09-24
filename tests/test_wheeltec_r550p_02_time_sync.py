import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import unittest
from unittest import mock

PROFILE = Path(__file__).resolve().parents[1] / 'devices/wheeltec_r550p/profiles/wheeltec_r550p_02'
spec = importlib.util.spec_from_file_location('ugv004_sntp', PROFILE / 'scripts/ccs_sntp_sync.py')
sntp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sntp)


class TimeSyncTests(unittest.TestCase):
    def result(self, offset):
        return dict(server='192.168.50.101', offset_seconds=offset, round_trip_seconds=0.02)

    def run_main(self, responses, wait=3):
        now = [0.0]
        def sleep(seconds):
            now[0] += seconds
        with mock.patch.object(sntp.sys, 'argv', ['sntp', '--wait-sync', str(wait), '--max-offset', '0.5']), \
             mock.patch.object(sntp, 'query', side_effect=responses) as query, \
             mock.patch.object(sntp.time, 'monotonic', side_effect=lambda: now[0]), \
             mock.patch.object(sntp.time, 'sleep', side_effect=sleep), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = sntp.main()
        return code, query, now[0]

    def test_waits_for_1970_clock_to_converge(self):
        code, query, elapsed = self.run_main([self.result(1_790_000_000), self.result(0.01)])
        self.assertEqual(code, 0)
        self.assertEqual(query.call_count, 2)
        self.assertEqual(elapsed, 1)

    def test_reachable_but_wrong_clock_fails_at_deadline(self):
        code, query, elapsed = self.run_main([self.result(50)] * 3)
        self.assertNotEqual(code, 0)
        self.assertEqual(elapsed, 3)
        self.assertEqual(query.call_count, 3)
        self.assertEqual(query.call_args.args[1], 1)

    def test_temporary_unavailability_recovers(self):
        code, _, _ = self.run_main([OSError('timeout'), self.result(-0.02)])
        self.assertEqual(code, 0)

    def test_unavailable_server_times_out(self):
        code, _, elapsed = self.run_main([OSError('timeout')] * 3)
        self.assertNotEqual(code, 0)
        self.assertEqual(elapsed, 3)

    def test_offset_only_keeps_existing_failure_code(self):
        code, query, elapsed = self.run_main([self.result(-1)], wait=0)
        self.assertEqual(code, 2)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(elapsed, 0)

    def response_socket(self, synchronized=True, matched=True):
        sock = mock.MagicMock()
        sock.__enter__.return_value = sock
        sock.getpeername.return_value = ('192.168.50.101', 123)
        def receive(_):
            packet = bytearray(48)
            packet[0] = 0x24 if synchronized else 0xE4
            packet[1] = 1
            packet[24:32] = sock.send.call_args.args[0][40:48] if matched else bytes(8)
            packet[32:40] = struct.pack('!II', 1_800_000_000 + sntp.NTP_DELTA, 0)
            packet[40:48] = packet[32:40]
            return packet
        sock.recv.side_effect = receive
        return sock

    def test_clock_step_during_packet_exchange_is_rejected(self):
        with mock.patch.object(sntp.socket, 'socket', return_value=self.response_socket()), \
             mock.patch.object(sntp.time, 'time', side_effect=[10, 1_800_000_000]), \
             mock.patch.object(sntp.time, 'monotonic', side_effect=[0, 0.02]):
            with self.assertRaisesRegex(RuntimeError, 'local clock changed'):
                sntp.query('192.168.50.101', 3)

    def test_offset_and_response_validation(self):
        for synchronized, matched in [(True, True), (False, True), (True, False)]:
            with self.subTest(synchronized=synchronized, matched=matched), \
                 mock.patch.object(sntp.socket, 'socket', return_value=self.response_socket(synchronized, matched)), \
                 mock.patch.object(sntp.time, 'time', side_effect=[1_800_000_000, 1_800_000_000.02]), \
                 mock.patch.object(sntp.time, 'monotonic', side_effect=[0, 0.02]):
                if synchronized and matched:
                    self.assertAlmostEqual(sntp.query('192.168.50.101', 3)['offset_seconds'], -0.01, places=5)
                else:
                    with self.assertRaises(RuntimeError):
                        sntp.query('192.168.50.101', 3)


if __name__ == '__main__':
    unittest.main()
