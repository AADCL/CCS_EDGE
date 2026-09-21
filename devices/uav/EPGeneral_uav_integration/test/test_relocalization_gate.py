import tempfile,threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
from epgeneral_relocalization.node import RelocalizationNode

class RelocalizationGateTests(unittest.TestCase):
    def test_new_negotiation_requires_live_localization(self):
        with tempfile.TemporaryDirectory() as root:
            n=object.__new__(RelocalizationNode)
            n.config=dict(backend='ducted_uav',enabled=True,map_root=root,pcd_filename='public_map.pcd')
            n.lock=threading.RLock();n.identity=None;n.operation_generation=0;n.ros=None
            n.stack=SimpleNamespace(stop=lambda:None)
            n._read_active_state=lambda:dict(map_id='m',status='localized',map_from_odom={'x':1})
            writes=[];replies=[]
            n._write_active_state=lambda *x:writes.append(x)
            n._reply=lambda *x:replies.append(x)
            with patch('epgeneral_relocalization.node.validate_map_directory'):
                n._negotiate(dict(map_id='m',device_id='UAV_001',session_id='new',request_id='request',payload={}))
            self.assertEqual(n.state,'map_ready')
            self.assertEqual(writes[-1],('m','map_ready'))
    def test_shutdown_never_resurrects_failed_localization(self):
        n=object.__new__(RelocalizationNode);n.config=dict(backend='ducted_uav');n.state='error'
        n._tf_dirty=True;n._latest_tf={'x':1};n._latest_tf_map_id='m'
        n._write_active_state=lambda *args:self.fail('must preserve error state')
        n._persist_latest_tf()
