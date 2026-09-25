import json
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
EDGE = ROOT
PROFILE = EDGE / 'devices/wheeltec_r550p/profiles/wheeltec_r550p_02'
for package in ('EPGeneral_device_config', 'EPGeneral_map_stream', 'EPGeneral_relocalization',
                'EPGeneral_task_control', 'EPGeneral_udp_telemetry', 'epgeneral_mqtav'):
    sys.path.insert(0, str(EDGE / package / 'src'))


class Wheeltec02Tests(unittest.TestCase):
    def setUp(self):
        self.config = {p.stem: yaml.safe_load(p.read_text(encoding='utf-8'))
                       for p in (PROFILE / 'config').glob('*.yaml')}

    def test_loaders_and_managed_commands_use_v51(self):
        import importlib
        from epgeneral_map_stream.config import build_integration_commands
        for module, name in (('epgeneral_mqtav', 'epgeneral_mqtav'),
                             ('epgeneral_udp_telemetry', 'udp_telemetry'),
                             ('epgeneral_map_stream', 'map_stream'),
                             ('epgeneral_relocalization', 'relocalization'),
                             ('epgeneral_task_control', 'task_control')):
            config = importlib.import_module(module + '.config').load_config(
                str(PROFILE / 'config' / (name + '.yaml')), str(PROFILE / 'config/device.yaml'))
            if name == 'map_stream':
                commands = build_integration_commands(config, dict(
                    session_dir='/tmp/session', map_name='20260912_120000',
                    pcd_path='/tmp/session/map.pcd', pgm_path='/tmp/session/map.pgm',
                    yaml_path='/tmp/session/map.yaml'))
                for launch in ('fastlio_mapping_wheeltec', 'pointcloud_mapper', 'tf_manager', 'pose_adapter'):
                    self.assertIn(launch + '.launch.xml', commands['start_fast_lio'])

    def test_calibration_composes_sensor_with_base_pose(self):
        from epgeneral_map_stream.processing import sensor_points_to_map
        sensor = self.config['map_stream']['ros']['body_from_sensor']
        # Base yaw=90deg and translation (2,3,0): sensor origin should become
        # (2,3.1,.15), and a point along its x axis should tilt down by 20deg.
        pose = dict(x=2., y=3., z=0., qx=0., qy=0., qz=2**-.5, qw=2**-.5)
        result = sensor_points_to_map(np.array([[0,0,0], [1,0,0]], dtype=float), pose, sensor)
        np.testing.assert_allclose(result[0], [2,3.1,.15], atol=1e-6)
        np.testing.assert_allclose(result[1], [2,3.1+np.cos(np.deg2rad(20)),.15-np.sin(np.deg2rad(20))], atol=1e-6)

    def test_identity_paths_and_platform_frames(self):
        self.assertEqual(self.config['device']['device'], {'id':'UGV_004','ip':'192.168.50.123'})
        task = self.config['task_control']['adapter']; storage = self.config['relocalization']['storage']
        pgm = next(x['source'] for x in self.config['udp_telemetry']['descriptors'] if x['name']=='pgm_mapping')
        self.assertEqual(task['active_map_state_file'], storage['active_map_state_file'])
        self.assertEqual(pgm['state_file'], storage['active_map_state_file'])
        self.assertEqual(task['navigation_map_root'], storage['map_root'])
        self.assertEqual(pgm['map_root'], storage['map_root'])
        frames = json.loads((ROOT/'tests/fixtures/ugv004_contract.json').read_text())['frames']
        self.assertEqual(frames, dict(remote_mapping='odom',preview_source='odom',remote_artifact='map'))
        device = json.loads((ROOT/'tests/fixtures/ugv004_contract.json').read_text())['device']
        self.assertEqual(device['relocalization_profile'], 'wheeltec_r550p')

    def test_navigation_keeps_live_obstacles_without_terrain_file_dependency(self):
        launch = ElementTree.parse(EDGE/'EPGeneral_task_control/launch/wheeltec_ccs_2d_navigation_v51.launch').getroot()
        self.assertEqual({x.get('name') for x in launch.findall('arg')},
                         {'map_name','map_dir','nav_map_yaml','odom_topic','cmd_vel_topic'})
        nodes = launch.findall('node')
        self.assertEqual({x.get('pkg') for x in nodes}, {'map_server','move_base'})
        move = next(x for x in nodes if x.get('pkg')=='move_base')
        plugins = yaml.safe_load(move.find("rosparam[@param='global_costmap/plugins']").text)
        self.assertEqual([x['type'] for x in plugins], ['costmap_2d::StaticLayer','costmap_2d::InflationLayer'])
        self.assertTrue(any('local_costmap_slope.yaml' in x.get('file','') for x in move.findall('rosparam')))
        guard = next(x for x in launch.findall('include') if 'wheeltec_terrain_filter' in x.get('file'))
        self.assertEqual(guard.find("arg[@name='enable_guard']").get('value'), 'true')

    def test_base_and_video_do_not_start_algorithm_stacks(self):
        launch = ElementTree.parse(PROFILE/'launch/wheeltec_r550p_02_base.launch').getroot()
        self.assertEqual(len(launch.findall('include')), 2)
        self.assertTrue(self.config['video']['enabled'])
        self.assertEqual(self.config['video']['rotation_degrees'], 0)
        bringup = ElementTree.parse(PROFILE/'launch/wheeltec_r550p_02_bringup.launch').getroot()
        self.assertEqual(bringup.find("arg[@name='enable_video']").get('default'), 'true')
        script = (PROFILE/'start_ccs_edge_dev.sh').read_text()
        self.assertNotIn('epgeneral_video_srt.launch', script)
        self.assertNotIn('/go2_sdk_bridge_real/enable', script)


if __name__ == '__main__':
    unittest.main()
