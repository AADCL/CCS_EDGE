import copy,json,math,tempfile,unittest
from pathlib import Path
import numpy as np
from epgeneral_uav_integration.core import FlightWorkflow,mission,transform_matrix,validate_pose_agreement
from epgeneral_uav_integration.maps import export,read_pcd

class CoreTests(unittest.TestCase):
    def status(self,**kw):
        s=dict(armed=False,landed_state=1,task_phase='IDLE_GROUND',task_generation=0,
               fcu_mode='POSCTL',waypoint_count=2,current_waypoint=0,reason='')
        s.update(kw);return s
    def test_schedule_takeoff_hover_path_completion(self):
        f=FlightWorkflow(2,100)
        self.assertEqual(f.tick(99,self.status(),True),[])
        self.assertEqual(f.tick(100,self.status(),True),[1])
        self.assertEqual(f.tick(101,self.status(task_phase='TAKEOFF'),True),[])
        self.assertEqual(f.tick(102,self.status(armed=True,task_phase='HOLDING',fcu_mode='OFFBOARD',task_generation=1),True),[2])
        f.tick(103,self.status(armed=True,task_phase='GUIDING',fcu_mode='OFFBOARD',task_generation=1),True)
        f.tick(104,self.status(armed=True,task_phase='HOLDING',fcu_mode='OFFBOARD',task_generation=1,current_waypoint=1,reason='mission complete; waiting for state=3'),True)
        self.assertEqual(f.phase,'completed')
        self.assertEqual(f.tick(105,{},False),[])
    def test_missing_localization_latches_failure(self):
        f=FlightWorkflow(2,100)
        self.assertEqual(f.tick(99,{},False),[0])
        self.assertEqual(f.tick(100,self.status(),True),[])
        self.assertEqual(f.phase,'failed')
    def test_takeoff_timeout_and_airborne_start(self):
        f=FlightWorkflow(2,100);f.tick(100,self.status(),True)
        self.assertEqual(f.tick(141,self.status(task_phase='TAKEOFF'),True),[0])
        f=FlightWorkflow(2,100)
        self.assertEqual(f.tick(100,self.status(armed=True),True),[0])
    def test_generation_change_rejected(self):
        f=FlightWorkflow(2,100);f.phase='running';f.generation=1
        self.assertEqual(f.tick(101,self.status(armed=True,task_phase='GUIDING',fcu_mode='OFFBOARD',task_generation=2),True),[0])
    def test_transform_and_identity(self):
        ident=dict(task_id='t',subtask_id='s',device_id='UAV_001',revision=1,map_id='m',frame_id='map')
        payload=dict(ident,task_type='air',cruise_speed_mps=.3,start_delay_seconds=0,
                     waypoints=[dict(index=0,x=1,y=0,z=2),dict(index=1,x=2,y=0,z=3)])
        t=transform_matrix([10,20,30],[0,0,math.sqrt(.5),math.sqrt(.5)])
        result,_,_=mission(payload,ident,t,[0,0,0])
        np.testing.assert_allclose([result['waypoints'][0][k] for k in ('x','y','z')],[10,21,32])
        bad=dict(payload,revision=2)
        with self.assertRaises(ValueError):mission(bad,ident,t,[0,0,0])
        with self.assertRaises(ValueError):mission(dict(payload,cruise_speed_mps=.31),ident,t,[0,0,0])
    def test_map_export_uses_observed_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'raw.pcd'
            src.write_text('VERSION .7\nFIELDS x y z intensity\nSIZE 4 4 4 4\nTYPE F F F F\nCOUNT 1 1 1 1\nWIDTH 2\nHEIGHT 1\nPOINTS 2\nDATA ascii\n0 0 0 1\n1 0 1 2\n')
            dest=Path(tmp)/'export'
            export(src,dest,transform_matrix([2,3,4],[0,0,0,1]))
            np.testing.assert_allclose(read_pcd(dest/'map.pcd'),[[2,3,4],[3,3,5]])
            self.assertEqual(json.loads((dest/'transform.json').read_text())['frame_id'],'odom')
            self.assertIn(bytes([205]),(dest/'map.pgm').read_bytes())

    def test_pose_agreement_rejects_nan_misalignment_and_bad_quaternion(self):
        validate_pose_agreement([0,0,0],[0,0,0,1],[0,0,0],[0,0,0,1])
        for pos,quat in [([float('nan'),0,0],[0,0,0,1]),([.2,0,0],[0,0,0,1]),
                         ([0,0,0],[0,0,0,0]),([0,0,0],[0,0,1,0])]:
            with self.assertRaises(ValueError):
                validate_pose_agreement(pos,quat,[0,0,0],[0,0,0,1])
