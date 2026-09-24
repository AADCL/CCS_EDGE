"""RTSP backend. Configuration and plugin checks happen before importing GI."""
import json
import time
from .config import listener_uri


def pipeline_description(c):
    codec = c["rtsp_codec"]
    rotation = " ! videoflip method=rotate-180" if c["rotation_degrees"] == 180 else ""
    return ('rtspsrc location="%s" protocols=%s latency=%d drop-on-latency=true '
            '! rtp%sdepay ! %sparse ! avdec_%s%s ! videoconvert ! videoscale ! videorate '
            '! video/x-raw,format=I420,width=%d,height=%d,framerate=%d/1 '
            '! identity name=frame_watch ! queue max-size-buffers=2 leaky=downstream '
            '! x264enc name=encoder tune=zerolatency speed-preset=ultrafast bitrate=%d key-int-max=%d bframes=0 byte-stream=true aud=true '
            '! video/x-h264,profile=baseline ! h264parse config-interval=-1 '
            '! mpegtsmux alignment=7 ! srtsink name=output uri="%s" latency=%d sync=false') % (
                c["rtsp_uri"], c["rtsp_transport"], c["rtsp_latency_ms"], codec, codec, codec, rotation,
                c["output_width"], c["output_height"], c["framerate"], c["bitrate_kbps"],
                c["framerate"], listener_uri(c), c["srt_latency_ms"])


def run(c, remaps):
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstVideo", "1.0")
    from gi.repository import Gst, GstVideo
    import rospy
    from std_msgs.msg import String
    rospy.init_node("epgeneral_video_srt", argv=["epgeneral_video_srt"] + remaps)
    Gst.init(None)
    pub = rospy.Publisher(c["runtime"]["status_topic"], String, queue_size=1, latch=True)
    description = pipeline_description(c)
    total = [0]
    reconnects = 0
    try:
        while not rospy.is_shutdown():
            pipe = None
            frames = [0]
            last = [time.monotonic()]
            def status(ready, error=""):
                return json.dumps(dict(device_id=c["device_id"], input_mode="rtsp", ready=ready,
                                       frames=total[0], frame_age=max(0, time.monotonic()-last[0]),
                                       reconnects=reconnects, error=error))
            try:
                pipe = Gst.parse_launch(description)
                sink = pipe.get_by_name("output")
                sink.set_property("latency", c["srt_latency_ms"])
                if sink.find_property("wait-for-connection"):
                    sink.set_property("wait-for-connection", False)
                def caller_added(*unused):
                    event = GstVideo.video_event_new_upstream_force_key_unit(Gst.CLOCK_TIME_NONE, True, 0)
                    pipe.get_by_name("encoder").get_static_pad("src").send_event(event)
                sink.connect("caller-added", caller_added)
                def received(pad, info):
                    last[0] = time.monotonic()
                    total[0] += 1
                    frames[0] += 1
                    return Gst.PadProbeReturn.OK
                pipe.get_by_name("frame_watch").get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, received)
                if pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                    raise RuntimeError("playing_failed")
                rospy.loginfo("RTSP/SRT started device=%s listener=%s:%d", c["device_id"], c["srt_bind_address"], c["srt_port"])
                bus = pipe.get_bus()
                published = 0
                while not rospy.is_shutdown():
                    message = bus.timed_pop_filtered(100*Gst.MSECOND, Gst.MessageType.ERROR | Gst.MessageType.EOS)
                    if message:
                        raise RuntimeError("pipeline_error" if message.type == Gst.MessageType.ERROR else "end_of_stream")
                    now = time.monotonic()
                    if now-last[0] > c["frame_timeout_seconds"]:
                        raise RuntimeError("frame_timeout")
                    if now-published >= 1:
                        pub.publish(status(frames[0] > 0))
                        published = now
            except Exception as exc:
                # Gst errors/debug strings may contain URI credentials.
                reason = str(exc) if str(exc) in ("playing_failed", "pipeline_error", "end_of_stream", "frame_timeout") else type(exc).__name__
                rospy.logerr("RTSP/SRT reconnect device=%s reason=%s", c["device_id"], reason)
                pub.publish(status(False, reason))
            finally:
                if pipe is not None:
                    pipe.set_state(Gst.State.NULL)
            reconnects += 1
            deadline = time.monotonic() + c["runtime"]["reconnect_interval_seconds"]
            while not rospy.is_shutdown() and time.monotonic() < deadline:
                time.sleep(min(0.1, max(0, deadline-time.monotonic())))
    finally:
        pub.unregister()
    return 0
