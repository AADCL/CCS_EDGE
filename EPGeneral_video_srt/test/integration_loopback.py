#!/usr/bin/env python3
"""Opt-in loopback integration smoke test. Requires an isolated ROS master."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
import unittest
import yaml
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GstRtspServer, GLib
import rospy
from sensor_msgs.msg import Image, CompressedImage
from std_msgs.msg import String
import cv2
import numpy as np

Gst.init(None)

class LoopbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert os.environ.get("ROS_MASTER_URI") == "http://127.0.0.1:11331", "isolated master required"
        rospy.init_node("video_generic_smoke", disable_signals=True)
        cls.root = Path(tempfile.mkdtemp(prefix="video-smoke-"))
        cls.loop = GLib.MainLoop()
        cls.thread = threading.Thread(target=cls.loop.run, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.loop.quit()
        cls.thread.join(5)
        rospy.signal_shutdown("smoke complete")

    def check_stream(self, mode, port, codec=None):
        folder = self.root / (mode + (codec or ""))
        folder.mkdir()
        c = dict(schema_version=2, enabled=True, input_mode=mode,
                 image_topic="/test/image", output_width=160, output_height=120,
                 framerate=10, bitrate_kbps=500, rotation_degrees=180,
                 srt_bind_address="127.0.0.1", srt_port=port, srt_latency_ms=120,
                 frame_timeout_seconds=2.0,
                 runtime=dict(status_topic="/test/video_status", reconnect_interval_seconds=0.3))
        server = None
        server_id = None
        if mode == "rtsp":
            server = GstRtspServer.RTSPServer()
            server.set_address("127.0.0.1")
            server.set_service(str(port+100))
            factory = GstRtspServer.RTSPMediaFactory()
            encoder = "x264enc tune=zerolatency speed-preset=ultrafast" if codec == "h264" else "x265enc tune=zerolatency speed-preset=ultrafast"
            factory.set_launch("( videotestsrc is-live=true pattern=smpte ! video/x-raw,width=160,height=120,framerate=10/1 ! videoconvert ! "+encoder+" ! rtp"+codec+"pay name=pay0 pt=96 )")
            factory.set_shared(True)
            server.get_mount_points().add_factory("/test", factory)
            server_id = server.attach(None)
            self.assertTrue(server_id)
            c["runtime"]["decoder_preload"] = os.environ.get("CCS_VIDEO_TEST_PRELOAD", "").split(":") if os.environ.get("CCS_VIDEO_TEST_PRELOAD") else []
            c.update(rtsp_uri="rtsp://127.0.0.1:%d/test" % (port+100), rtsp_codec=codec)
        (folder/"device.yaml").write_text(yaml.safe_dump(dict(schema_version=1, device=dict(id="SMOKE_DEVICE", ip="127.0.0.1"))))
        (folder/"video.yaml").write_text(yaml.safe_dump(c))
        states = []
        sub = rospy.Subscriber("/test/video_status", String, lambda m: states.append(json.loads(m.data)))
        publisher = rospy.Publisher("/test/image", Image if mode == "ros_image" else CompressedImage, queue_size=1) if mode != "rtsp" else None
        # Opposing halves make the 180-degree output rotation observable after lossy encoding.
        raw = np.zeros((120, 160, 3), dtype=np.uint8)
        raw[:60,:] = [0, 0, 255]
        raw[60:,:] = [255, 0, 0]
        payload = raw.tobytes() if mode == "ros_image" else cv2.imencode(".jpg", raw)[1].tobytes()
        receiver = None
        process = None
        log = open(folder/"node.log", "w")
        try:
            child_env = dict(os.environ)
            child_env.pop("LD_PRELOAD", None)  # Exercise YAML preload in the backend.
            process = subprocess.Popen(["roslaunch", "epgeneral_video_srt", "epgeneral_video_srt.launch",
                "config_dir:="+str(folder)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=child_env)
            # No caller during startup: stream must not block waiting for a viewer.
            started = time.monotonic()
            def publish():
                if publisher:
                    if mode == "ros_image":
                        message = Image(height=120, width=160, encoding="bgr8", step=480, data=payload)
                    else:
                        message = CompressedImage(format="jpeg", data=payload)
                    message.header.stamp = rospy.Time.now()
                    publisher.publish(message)
            while time.monotonic()-started < 4:
                publish()
                time.sleep(0.07)
            self.assertIsNone(process.poll(), (folder/"node.log").read_text())
            uri = "srt://127.0.0.1:%d?mode=caller&transtype=live" % port
            description = 'srtsrc uri="%s" latency=120 ! tsdemux ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! appsink name=frames sync=false max-buffers=2 drop=true' % uri
            receiver = Gst.parse_launch(description)
            receiver.set_state(Gst.State.PLAYING)
            sink = receiver.get_by_name("frames")
            received = 0
            sample_data = None
            deadline = time.monotonic()+12
            while time.monotonic() < deadline and received < 25:
                publish()
                sample = sink.emit("try-pull-sample", 70*Gst.MSECOND)
                if sample:
                    received += 1
                    caps = sample.get_caps().get_structure(0)
                    self.assertEqual((caps.get_value("width"),caps.get_value("height")), (160,120))
                    buffer = sample.get_buffer()
                    sample_data = np.frombuffer(buffer.extract_dup(0, buffer.get_size()), dtype=np.uint8).reshape(120,160,3)
                else: time.sleep(0.01)
            self.assertGreaterEqual(received,25,(folder/"node.log").read_text())
            self.assertTrue(any(s["ready"] and s["device_id"]=="SMOKE_DEVICE" for s in states),states)
            if publisher:
                self.assertGreater(float(sample_data[20,:,0].mean()), float(sample_data[20,:,2].mean())+100)
                self.assertGreater(float(sample_data[100,:,2].mean()), float(sample_data[100,:,0].mean())+100)
            # Interrupt either input, require failed status, then resume the same listener.
            if server:
                server.get_mount_points().remove_factory("/test")
                def disconnect(unused, client):
                    client.close()
                    return GstRtspServer.RTSPFilterResult.REMOVE
                server.client_filter(disconnect)
            if publisher or server:
                receiver.set_state(Gst.State.NULL)
                time.sleep(4)
                self.assertTrue(any(not s["ready"] for s in states),states)
                if server:
                    server.get_mount_points().add_factory("/test", factory)
                receiver = Gst.parse_launch(description)
                receiver.set_state(Gst.State.PLAYING)
                sink=receiver.get_by_name("frames")
                resumed = 0
                deadline=time.monotonic()+12
                while time.monotonic()<deadline and resumed<10:
                    publish()
                    sample=sink.emit("try-pull-sample",70*Gst.MSECOND)
                    if sample: resumed+=1
                self.assertGreaterEqual(resumed,10,(folder/"node.log").read_text())
                self.assertTrue(any(s["reconnects"]>0 and s["ready"] for s in states),states)
            print(json.dumps(dict(mode=mode, codec=codec, frames=received, rotation_verified=bool(publisher),
                 reconnect_verified=True, states=states[-3:])), flush=True)
        finally:
            if receiver: receiver.set_state(Gst.State.NULL)
            if process and process.poll() is None:
                os.killpg(process.pid,signal.SIGINT)
                try:process.wait(12)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
            log.close()
            sub.unregister()
            if publisher:publisher.unregister()
            if server_id:GLib.source_remove(server_id)

    def test_raw(self): self.check_stream("ros_image",19101)
    def test_compressed(self): self.check_stream("ros_compressed",19102)
    def test_rtsp_h264(self): self.check_stream("rtsp",19103,"h264")
    def test_rtsp_h265(self): self.check_stream("rtsp",19104,"h265")

if __name__ == "__main__": unittest.main(verbosity=2)
