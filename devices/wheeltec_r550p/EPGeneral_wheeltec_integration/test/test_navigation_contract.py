import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
for task_source in (ROOT.parent / 'EPGeneral_task_control/src',
                    ROOT.parents[2] / 'EPGeneral_task_control/src'):
    if task_source.is_dir():
        sys.path.insert(0, str(task_source))
        break
from epgeneral_wheeltec_integration.readiness import driver_velocity_link
from epgeneral_task_control.config import load_config


class NavigationContractTests(unittest.TestCase):
    def test_direct_driver_chain_preserves_native_terrain_navigation(self):
        tree = ElementTree.parse(ROOT / 'launch/native_navigation_components.launch').getroot()
        include = tree.find('include')
        self.assertIn('navigation_teb.launch', include.attrib['file'])
        args = {item.attrib['name']: item.attrib['value'] for item in include.findall('arg')}
        self.assertEqual(args['cmd_vel_topic'], '$(arg cmd_vel_topic)')
        self.assertEqual(args['terrain_map_yaml'], '$(arg map_dir)/native_v60/terrain_2p5d.yaml')
        self.assertFalse(any(node.attrib.get('pkg') == 'wheeltec_safety' for node in tree.findall('node')))
        profile = ROOT.parent / 'profiles/wheeltec_r550p/config'
        if not profile.is_dir():
            profile = ROOT.parents[1] / 'config/wheeltec_r550p'
        config = yaml.safe_load((profile / 'task_control.yaml').read_text())['adapter']
        loaded = load_config(
            str(profile / 'task_control.yaml'),
            str(profile / 'device.yaml'))
        self.assertFalse(loaded['adapter']['control_authority']['safety_gate_enabled'])
        self.assertEqual(config['navigation_cmd_vel_topic'], '/wheeltec_driver/cmd_vel')
        self.assertFalse(config['control_authority']['safety_gate_enabled'])
        self.assertNotIn('safety_stop_service', config['control_authority'])
        self.assertTrue(config['auto_arm_on_schedule'])
        self.assertTrue(config['auto_disarm_on_terminal'])
        limits = yaml.safe_load((ROOT / 'config/planner_overrides.yaml').read_text())['TebLocalPlannerROS']
        self.assertEqual(limits['max_vel_x_backwards'], 0.15)
        self.assertEqual(limits['max_vel_x'], 0.20)
        self.assertEqual(limits['max_vel_theta'], 0.40)

    def test_readiness_rejects_wrong_driver_link_or_old_gate(self):
        topic = '/wheeltec_driver/cmd_vel'
        good = ([[topic, ['/move_base']]], [[topic, ['/wheeltec_robot']]], [])
        self.assertTrue(driver_velocity_link(good, topic)[0])
        self.assertFalse(driver_velocity_link(([], good[1], []), topic)[0])
        self.assertFalse(driver_velocity_link((good[0], [], []), topic)[0])
        self.assertFalse(driver_velocity_link(([[topic, ['/move_base', '/wheeltec_safety']]], good[1], []), topic)[0])


if __name__ == '__main__':
    unittest.main()
