import io
import tempfile
import threading
import time
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np
from epgeneral_map_stream.artifacts import ArtifactHttpServer, write_binary_pcd
from epgeneral_map_stream.preview import PreviewByteBudget, bounded_preview, pcd_header
try:
    from . import test_node as _node_fixture
except ImportError:
    import test_node as _node_fixture


class PreviewTests(unittest.TestCase):
    def test_dense_cloud_and_exact_binary_budget(self):
        rng = np.random.default_rng(7)
        cloud = rng.uniform(-50,50,(100000,3))
        cloud = np.concatenate((cloud,cloud,[[np.nan,0,0],[np.inf,0,0]]))
        points = bounded_preview(cloud,.1,500000)
        self.assertGreater(len(points),40000)
        self.assertEqual(len(np.unique(np.floor(points.astype(float)/.1),axis=0)),len(points))
        self.assertTrue(np.all(points.min(axis=0)<-49))
        self.assertTrue(np.all(points.max(axis=0)>49))
        with tempfile.TemporaryDirectory() as root:
            descriptor=write_binary_pcd(str(Path(root)/"preview.pcd"),points)
            self.assertLessEqual(descriptor["byte_count"],500000)
            self.assertEqual(descriptor["byte_count"],len(pcd_header(len(points)))+len(points)*12)

    def test_sparse_negative_voxels_and_empty(self):
        points=bounded_preview(np.array([[-.11,0,0],[-.12,0,0],[.01,0,0],[.02,0,0]]),.1,1024)
        self.assertEqual(len(points),2)
        self.assertEqual(bounded_preview(np.empty((0,3)),.1,1024).shape,(0,3))

    def test_actual_concurrent_http_get_and_range_share_rolling_budget(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"bytes.pcd"
            data=bytes(range(256))*256
            path.write_bytes(data)
            server=ArtifactHttpServer("127.0.0.1",0,preview_bytes_per_second=65536)
            records=[]
            original=server.preview_budget.write
            def write(stream,chunk):
                class Recorder:
                    def write(self,body):
                        stream.write(body)
                        records.append((time.monotonic(),len(body)))
                original(Recorder(),chunk)
            server.preview_budget.write=write
            server.start()
            self.addCleanup(server.close)
            token,_=server.register(str(path),30,route="/mapping/preview/one.pcd")
            url=f"http://127.0.0.1:{server.port}/mapping/preview/one.pcd?token={token}"
            def get(range_value=None):
                request=urllib.request.Request(url,headers={"Range":range_value} if range_value else {})
                with urllib.request.urlopen(request,timeout=5) as response:
                    return response.read()
            with ThreadPoolExecutor(3) as pool:
                a=pool.submit(get)
                b=pool.submit(get)
                c=pool.submit(get,"bytes=32768-")
                self.assertEqual(a.result(),data)
                self.assertEqual(b.result(),data)
                self.assertEqual(c.result(),data[32768:])
            self.assertEqual(sum(n for _,n in records),163840)
            for stamp,_ in records:
                self.assertLessEqual(sum(n for t,n in records if stamp-1<t<=stamp),65536)

    def test_unregistered_file_is_retained_during_active_read(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"preview.pcd";path.write_bytes(b"a"*20000)
            server=ArtifactHttpServer("127.0.0.1",0)
            server.start();self.addCleanup(server.close)
            token,_=server.register(str(path),30,route="/mapping/preview/one.pcd")
            entered,release=threading.Event(),threading.Event()
            original=server.preview_budget.write
            def block(stream,data):
                entered.set();release.wait(3);original(stream,data)
            server.preview_budget.write=block
            def get():
                with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/mapping/preview/one.pcd?token={token}",timeout=5) as response:
                    return response.read()
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(get)
                try:
                    self.assertTrue(entered.wait(2))
                    server.unregister(token,delete=True)
                    self.assertTrue(path.exists())
                finally:
                    release.set()
                self.assertEqual(future.result(),b"a"*20000)
            until=time.monotonic()+1
            while path.exists() and time.monotonic()<until:time.sleep(.01)
            self.assertFalse(path.exists())

    def test_closing_budget_wakes_waiting_writes(self):
        budget=PreviewByteBudget(8);stream=io.BytesIO()
        budget.write(stream,b"12345678")
        with ThreadPoolExecutor(1) as pool:
            pending=pool.submit(budget.write,stream,b"a")
            budget.close()
            with self.assertRaises(OSError):pending.result(timeout=1)


class PreviewNodeTests(unittest.TestCase):
    setUp=_node_fixture.NodeTests.setUp
    prepare=_node_fixture.NodeTests.prepare
    start=_node_fixture.NodeTests.start
    command=_node_fixture.NodeTests.command
    messages=_node_fixture.NodeTests.messages

    def test_full_point_buffer_does_not_flush_before_one_second(self):
        self.prepare();self.start()
        session=self.node.session
        self.config["max_window_points"]=2
        pose=type("Pose",(),{"transform":dict(x=0,y=0,z=0,qx=0,qy=0,qz=0,qw=1)})()
        with patch("epgeneral_map_stream.node.extract_pointcloud2",return_value=np.array([[1,0,0],[2,0,0]])):
            for i in range(5):
                self.clock_value[0]=10+i*.1
                self.node._process_cloud(session.token,session,object(),i+1,pose,self.clock_value[0])
        self.assertTrue(self.node.preview_queue.empty())
        self.assertLessEqual(session.window_points,2)
        self.clock_value[0]=11.01
        self.node._flush_window(session,session.token)
        self.assertEqual(self.node.preview_queue.qsize(),1)

    def test_latest_window_replaces_pending_without_unfinished_task_leak(self):
        self.prepare();self.start();session=self.node.session
        for i in range(4):
            self.clock_value[0]=20+i*2
            session.window_started_at=self.clock_value[0]-1.1
            session.scans=[i]
            self.node._flush_window(session,session.token)
        self.assertEqual(self.node.preview_queue.qsize(),1)
        self.assertEqual(self.node.preview_queue.get_nowait()[2],[3])
        self.node.preview_queue.task_done()
        self.assertEqual(self.node.preview_queue.unfinished_tasks,0)

    def test_worker_publishes_at_most_once_per_second_and_uses_latest(self):
        self.prepare();self.start();session=self.node.session
        self.node.clock=time.monotonic
        self.node.running.set()
        published=[]
        original=self.node._send_session_message
        def send(owner,kind,payload):
            original(owner,kind,payload)
            if kind=="cloud_fragment_ready":published.append((time.monotonic(),payload["started_at_ns"]))
        self.node._send_session_message=send
        pose=dict(x=0,y=0,z=0,qx=0,qy=0,qz=0,qw=1)
        def enqueue(stamp):
            with self.node.lock:
                session.window_started_at=time.monotonic()-1.1
                session.scans=[(np.array([[1.,0,0]]),pose,stamp,pose)]
                self.node._flush_window(session,session.token)
        worker=threading.Thread(target=self.node._preview_loop,daemon=True)
        worker.start()
        try:
            enqueue(1)
            until=time.monotonic()+1
            while not published and time.monotonic()<until:time.sleep(.01)
            self.assertEqual(len(published),1)
            for stamp in range(2,15):enqueue(stamp)
            until=time.monotonic()+2
            while len(published)<2 and time.monotonic()<until:time.sleep(.01)
            self.assertEqual(len(published),2)
            self.assertGreaterEqual(published[1][0]-published[0][0],1.0)
            self.assertEqual(published[1][1],14)
        finally:
            session.state="cancelled"
            self.node.running.clear()
            worker.join(2)
