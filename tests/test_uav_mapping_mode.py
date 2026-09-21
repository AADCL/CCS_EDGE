"""UAV_001 mapping-mode permission contract without starting ROS or hardware."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

EDGE = Path(__file__).resolve().parents[1]
STAGE = EDGE / "devices/uav/EPGeneral_uav_integration/scripts/uav_stage_node.py"
SUPERVISOR = EDGE / "devices/uav/profiles/uav_001/scripts/supervisor.py"
BRINGUP = EDGE / "devices/uav/profiles/uav_001/launch/uav_001_bringup.launch"


def load_stage_module():
    rospy = types.ModuleType("rospy")
    rospy.set_param = mock.Mock()
    modules = {
        "rospy": rospy,
        "std_msgs": types.ModuleType("std_msgs"),
        "std_msgs.msg": types.SimpleNamespace(String=object),
        "mavros_msgs": types.ModuleType("mavros_msgs"),
        "mavros_msgs.msg": types.SimpleNamespace(State=object, ExtendedState=object),
        "epgeneral_uav_integration": types.ModuleType("epgeneral_uav_integration"),
        "epgeneral_uav_integration.srv": types.SimpleNamespace(
            StageCommand=object, StageCommandResponse=object),
        "epgeneral_uav_integration.core": types.SimpleNamespace(atomic_json=mock.Mock()),
    }
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("uav_stage_mapping_mode_test", STAGE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    module.rospy = rospy
    return module


class UavModeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_stage_module()

    def manager(self, mapping_enabled, execution_enabled):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        manager = self.module.Manager.__new__(self.module.Manager)
        manager.root = Path(directory.name)
        manager.mapping_enabled = mapping_enabled
        manager.execution_enabled = execution_enabled
        manager.stage = None
        manager.controller = None
        manager.flight_lock = manager.root / "flight_fault.json"
        manager.emergency_lock = manager.root / "emergency_stop.json"
        manager.ground = lambda: True
        manager.spawn = lambda name, owner, args: {
            "name": name, "owner": owner, "args": args,
            "process": types.SimpleNamespace(poll=lambda: None),
        }
        return manager

    def test_static_mode_rejects_mapping_and_flight(self):
        manager = self.manager(False, False)
        with self.assertRaisesRegex(RuntimeError, "mapping/localization disabled"):
            manager.apply("mapping_start", "operator", "")
        with self.assertRaisesRegex(RuntimeError, "flight control disabled"):
            manager.apply("controller_start", "operator", "{}")

    def test_mapping_mode_allows_mapping_and_localization_only(self):
        manager = self.manager(True, False)
        self.assertEqual(manager.apply("mapping_start", "operator", ""), "mapping started")
        self.assertEqual(manager.stage["args"], ["roslaunch", "ducted_bringup", "mapping.launch"])

        manager.stage = None
        map_file = manager.root / "fixture.pcd"
        map_file.write_text("fixture", encoding="utf-8")
        self.assertEqual(manager.apply("localization_start", "operator", str(map_file)),
                         "localization started")
        map_argument = next(item for item in manager.stage["args"] if item.startswith("map_file:="))
        self.assertEqual(Path(map_argument.split(":=", 1)[1]), map_file.resolve())
        with self.assertRaisesRegex(RuntimeError, "mapping mode: flight control disabled"):
            manager.apply("controller_start", "operator", "{}")

    def test_flight_mode_allows_mapping_and_controller(self):
        manager = self.manager(True, True)
        mission_file = manager.root / "mission.json"
        mission_file.write_text(json.dumps({"waypoints": []}), encoding="utf-8")
        manager.stage = {"name": "localization", "owner": "operator",
                         "process": types.SimpleNamespace(poll=lambda: None)}
        self.assertEqual(manager.apply("controller_start", "operator",
                                      json.dumps({"mission_file": str(mission_file), "speed": 0.2})),
                         "controller started without arming")
        self.assertIn("execution_mode:=direct", manager.controller["args"])

    def test_profile_exposes_separate_mapping_and_flight_permissions(self):
        root = ET.parse(BRINGUP).getroot()
        args = {item.attrib["name"]: item.attrib for item in root.findall("arg")}
        self.assertEqual(args["mapping_enabled"]["default"], "$(arg execution_enabled)")
        stage = next(node for node in root.findall("node")
                     if node.attrib.get("name") == "uav_stage_manager")
        stage_params = {item.attrib["name"]: item.attrib["value"] for item in stage.findall("param")}
        self.assertEqual(stage_params["mapping_enabled"], "$(arg mapping_enabled)")
        self.assertEqual(stage_params["execution_enabled"], "$(arg execution_enabled)")
        adapter = next(node for node in root.findall("node")
                       if node.attrib.get("name") == "uav_task_adapter")
        adapter_params = {item.attrib["name"]: item.attrib["value"] for item in adapter.findall("param")}
        self.assertNotIn("mapping_enabled", adapter_params)
        self.assertEqual(adapter_params["execution_enabled"], "$(arg execution_enabled)")

        supervisor = SUPERVISOR.read_text(encoding="utf-8")
        self.assertIn("mode.add_argument('--mapping'", supervisor)
        self.assertIn("'static' if a.static else 'mapping'", supervisor)
        self.assertIn("mapping_enabled=not a.static", supervisor)
        self.assertIn("execution_enabled=a.flight", supervisor)


if __name__ == "__main__":
    unittest.main(verbosity=2)
