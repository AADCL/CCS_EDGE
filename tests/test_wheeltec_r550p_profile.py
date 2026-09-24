import json
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'devices/wheeltec_r550p/profiles/wheeltec_r550p'


class WheeltecR550pProfileTests(unittest.TestCase):
    def test_identity_and_actual_topics(self):
        device = yaml.safe_load((PROFILE / 'config/device.yaml').read_text(encoding="utf-8"))
        mqtt = yaml.safe_load((PROFILE / 'config/epgeneral_mqtav.yaml').read_text(encoding="utf-8"))
        telemetry = yaml.safe_load((PROFILE / 'config/udp_telemetry.yaml').read_text(encoding="utf-8"))
        video = yaml.safe_load((PROFILE / 'config/video.yaml').read_text(encoding="utf-8"))
        self.assertEqual(device["device"], {"id": "UGV_003", "ip": "192.168.50.122"})
        self.assertEqual(mqtt["ros"]["state"]["topic"], "/odom")
        self.assertEqual(mqtt["ros"]["battery"]["topic"], "/PowerVoltage")
        self.assertEqual(mqtt["ros"]["battery"]["mapping"]["voltage"], "data")
        sources = {item["name"]: item["source"]["topic"] for item in telemetry["descriptors"]}
        self.assertEqual(sources["vision_pose"], "/fastlio_odom")
        self.assertEqual(sources["imu"], "/livox/imu")
        self.assertEqual(sources["fastlio2"], "/Odometry")
        self.assertTrue(video["enabled"])
        self.assertEqual(video["camera_model"], "Orbbec Gemini 336L")
        self.assertEqual(video["image_topic"], "/camera/color/image_raw")
        self.assertEqual(video["rotation_degrees"], 180)
        self.assertEqual(
            [video["output_width"], video["output_height"], video["framerate"],
             video["bitrate_kbps"], video["srt_port"]],
            [640, 360, 30, 2500, 9000],
        )

    def test_managed_mapping_backend_uses_wheeltec_nodes(self):
        package = ROOT / 'EPGeneral_map_stream'
        sys.path.insert(0, str(package / "src"))
        try:
            from epgeneral_map_stream.config import build_integration_commands, load_config
            config = load_config(
                str(PROFILE / 'config/map_stream.yaml'),
                str(PROFILE / 'config/device.yaml'),
            )
            commands = build_integration_commands(config, {
                "session_dir": "/tmp/wheeltec-session",
                "map_name": "20260827_120000",
                "pcd_path": "/tmp/wheeltec-session/map.pcd",
                "pgm_path": "/tmp/wheeltec-session/map.pgm",
                "yaml_path": "/tmp/wheeltec-session/map.yaml",
            })
        finally:
            sys.path.pop(0)
        self.assertEqual(config["integration_backend"], "managed_finalize")
        self.assertEqual(config["managed_mapper_node"], "/wheeltec_pointcloud_mapper")
        self.assertEqual(commands["start_fast_lio"][-5:], [
            "/laserMapping", "/wheeltec_pointcloud_mapper", "/wheeltec_tf_manager",
            "/wheeltec_geometry_tf_publisher", "/wheeltec_pose_adapter",
        ])


    def test_launch_and_one_click_script_start_gemini_video_by_default(self):
        launch = ElementTree.parse(PROFILE / 'launch/wheeltec_r550p_bringup.launch').getroot()
        args = {item.attrib["name"]: item.attrib.get("default") for item in launch.findall("arg")}
        self.assertEqual(args["enable_video"], "true")
        script = (PROFILE / "start_ccs_edge_dev.sh").read_text(encoding="utf-8")
        for value in (
            "/home/nrc19/ccs_edge_ws", "/home/nrc19/livox_fastlio/devel/setup.bash",
            "wheeltec_livox_base.launch", "/PowerVoltage", "/livox/lidar",
            "wheeltec_task_control.launch", "publish_zero_velocity",
            "CCS_ENABLE_VIDEO", "manage_ccs_video.sh", "/wheeltec_control/enable",
        ):
            self.assertIn(value, script)
        manager = (PROFILE / "manage_ccs_video.sh").read_text(encoding="utf-8")
        self.assertIn("epgeneral_video_srt camera.launch", manager)
        video = yaml.safe_load((PROFILE / "config/video.yaml").read_text(encoding="utf-8"))
        self.assertEqual(video["capture"]["launch"], "wheeltec_orbbec336l.launch")
        self.assertIn("/camera/color/image_raw", manager)
        self.assertIn("epgeneral_video_srt.launch", manager)

    def test_dedicated_navigation_launch_uses_2d_map_and_safety_gate(self):
        path = (ROOT / 'EPGeneral_task_control/launch/wheeltec_ccs_2d_navigation.launch')
        launch = path.read_text(encoding="utf-8")
        tree = ElementTree.parse(path).getroot()
        params = {
            item.attrib["name"]: item.attrib["value"]
            for item in tree.iter("param")
            if "name" in item.attrib and "value" in item.attrib
        }
        self.assertIn("map_server", launch)
        self.assertIn("$(arg nav_map_yaml)", launch)
        self.assertNotIn("terrain_2p5d.yaml", launch)
        self.assertIn("wheeltec_terrain_filter", launch)
        self.assertIn("cmd_vel_safety.launch", launch)
        self.assertIn("/nav_cmd_vel", launch)
        self.assertEqual(params["TebLocalPlannerROS/max_vel_x"], "0.20")
        reverse_bound = float(params["TebLocalPlannerROS/max_vel_x_backwards"])
        epsilon = float(params["TebLocalPlannerROS/penalty_epsilon"])
        # Cross-component contract: TEB saturation stays below the safety
        # gate's reverse fault threshold while retaining a valid penalty band.
        self.assertGreater(epsilon, 0.0)
        self.assertGreater(reverse_bound, epsilon)
        self.assertLess(reverse_bound, 0.02)
        self.assertEqual(params["TebLocalPlannerROS/allow_init_with_backwards_motion"], "false")
        self.assertEqual(params["TebLocalPlannerROS/use_proportional_saturation"], "false")
        self.assertEqual(params["TebLocalPlannerROS/max_vel_theta"], "0.40")
        self.assertEqual(
            params["TebLocalPlannerROS/weight_kinematics_forward_drive"],
            "1000.0",
        )

    def test_driver_patch_declares_baseline_and_control_authority(self):
        patch = (PROFILE / 'driver_patch/turn_on_wheeltec_robot_control_authority.patch').read_text(
                     encoding="utf-8")
        for value in (
            "ControlAuthorityLease", "control_heartbeat", "set_autonomous",
            "reset_authority", "BuildVelocityPacket",
        ):
            self.assertIn(value, patch)

    def test_safety_patch_is_baseline_checked_and_fixes_snapshot_starvation(self):
        patch_dir = PROFILE / "safety_patch"
        patch = (
            patch_dir / "wheeltec_safety_snapshot_and_reverse.patch"
        ).read_text(encoding="utf-8")
        manager = (patch_dir / "manage_safety_patch.sh").read_text(
            encoding="utf-8"
        )
        for value in (
            "with self.output_lock:",
            "self.run_cycle()",
            "sanitized_velocity",
            "linear_deadband: 0.02",
            "costmap_lethal_threshold: 100",
            "costmap_cell_blocks",
            "test_timer_serializes_complete_cycle_against_input_commits",
        ):
            self.assertIn(value, patch)
        for name in ("baseline.sha256", "patched.sha256"):
            lines = (patch_dir / name).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 7)
        self.assertIn("patch --dry-run", manager)
        self.assertIn("verify_manifest baseline.sha256", manager)
        self.assertIn("verify_manifest patched.sha256", manager)
        self.assertIn("catkin_make -j1 --pkg wheeltec_safety", manager)


if __name__ == "__main__":
    unittest.main()
