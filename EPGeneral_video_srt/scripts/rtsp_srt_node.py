#!/usr/bin/env python3
"""RTSP (including A8 HEVC) to baseline H.264/SRT with bounded reconnect."""
import json
import time
from urllib.parse import urlsplit
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst,GstVideo
import rospy
from std_msgs.msg import String

def pipeline_description(c):
    uri=c['rtsp_uri']; parsed=urlsplit(uri)
    if parsed.scheme!='rtsp' or not parsed.hostname or any(x in uri for x in ['"',chr(92),'\n','\r']):
        raise ValueError('invalid RTSP URL')
    for key,low,high in [('output_width',16,3840),('output_height',16,2160),('framerate',1,60),
                         ('bitrate_kbps',100,20000),('srt_port',1,65535),('srt_latency_ms',20,8000)]:
        if not isinstance(c[key],int) or not low<=c[key]<=high: raise ValueError('invalid '+key)
    codec=c.get('rtsp_codec','h265')
    if codec not in ('h264','h265'):raise ValueError('rtsp_codec must be h264 or h265')
    decoder='rtp%sdepay ! %sparse ! avdec_%s' % (codec,codec,codec)
    return ('rtspsrc location="%s" protocols=tcp latency=100 drop-on-latency=true '
        '! %s ! videoconvert ! videoscale ! videorate '
        '! video/x-raw,format=I420,width=%d,height=%d,framerate=%d/1 '
        '! identity name=frame_watch ! queue max-size-buffers=2 leaky=downstream '
        '! x264enc name=encoder tune=zerolatency speed-preset=ultrafast bitrate=%d key-int-max=%d bframes=0 '
        '! video/x-h264,profile=baseline ! h264parse config-interval=-1 '
        '! mpegtsmux alignment=7 ! srtsink name=output '
        'uri="srt://:%d?mode=listener&transtype=live" latency=%d sync=false') % (
        uri,decoder,c['output_width'],c['output_height'],c['framerate'],c['bitrate_kbps'],
        c['framerate'],c['srt_port'],c['srt_latency_ms'])

def main():
    rospy.init_node('epgeneral_video_srt')
    defaults=dict(rtsp_uri='',rtsp_codec='h265',output_width=640,output_height=480,framerate=15,
                  bitrate_kbps=2000,srt_port=9000,srt_latency_ms=120)
    cfg={k:rospy.get_param('~'+k,v) for k,v in defaults.items()}
    description=pipeline_description(cfg)
    timeout=float(rospy.get_param('~frame_timeout_seconds',8.0))
    if not 1<=timeout<=60: raise ValueError('frame timeout must be 1..60 seconds')
    Gst.init(None)
    pub=rospy.Publisher('~status',String,queue_size=1,latch=True)
    total=[0]; reconnects=0
    while not rospy.is_shutdown():
        pipe=None; frames=[0]
        try:
            pipe=Gst.parse_launch(description); sink=pipe.get_by_name('output')
            sink.set_property('latency',cfg['srt_latency_ms'])
            if sink.find_property('wait-for-connection'): sink.set_property('wait-for-connection',False)
            def caller_added(*args):
                event=GstVideo.video_event_new_upstream_force_key_unit(Gst.CLOCK_TIME_NONE,True,0)
                pipe.get_by_name('encoder').get_static_pad('src').send_event(event)
            sink.connect('caller-added',caller_added)
            last=[time.monotonic()]
            def received(pad,info):
                last[0]=time.monotonic();total[0]+=1;frames[0]+=1
                return Gst.PadProbeReturn.OK
            pipe.get_by_name('frame_watch').get_static_pad('src').add_probe(Gst.PadProbeType.BUFFER,received)
            if pipe.set_state(Gst.State.PLAYING)==Gst.StateChangeReturn.FAILURE: raise RuntimeError('PLAYING failed')
            rospy.loginfo('RTSP/SRT started input=%s listener=:%d',cfg['rtsp_uri'],cfg['srt_port'])
            bus=pipe.get_bus();published=0
            while not rospy.is_shutdown():
                m=bus.timed_pop_filtered(100*Gst.MSECOND,Gst.MessageType.ERROR|Gst.MessageType.EOS)
                if m:
                    if m.type==Gst.MessageType.ERROR:
                        error,debug=m.parse_error();raise RuntimeError(str(error)+' '+str(debug))
                    raise RuntimeError('RTSP end of stream')
                now=time.monotonic()
                if now-last[0]>timeout: raise RuntimeError('RTSP frame timeout')
                if now-published>=1:
                    pub.publish(json.dumps(dict(frames=total[0],frame_age=now-last[0],reconnects=reconnects,
                                                ready=frames[0]>0,input=cfg['rtsp_uri'])))
                    published=now
        except Exception as e:
            rospy.logerr('RTSP/SRT reconnect: %s',e)
            pub.publish(json.dumps(dict(ready=False,frames=total[0],error=str(e),reconnects=reconnects)))
        finally:
            if pipe: pipe.set_state(Gst.State.NULL)
        reconnects+=1;deadline=time.monotonic()+3
        while not rospy.is_shutdown() and time.monotonic()<deadline: time.sleep(.1)
if __name__=='__main__': main()
