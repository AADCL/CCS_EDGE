#!/usr/bin/env python3
import argparse
import time
import rospy
from epgeneral_wheeltec_integration.readiness import Readiness

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['base', 'navigation'])
    p.add_argument('--timeout', type=float, default=30)
    args = p.parse_args()
    rospy.init_node('ccs_readiness_check', anonymous=True, disable_signals=True)
    check = Readiness(args.mode)
    end = time.monotonic() + args.timeout
    reason = 'not checked'
    while time.monotonic() < end:
        ready, reason = check.check()
        if ready:
            print('READY: ' + reason)
            raise SystemExit(0)
        time.sleep(0.2)
    raise SystemExit('NOT_READY: ' + reason)
