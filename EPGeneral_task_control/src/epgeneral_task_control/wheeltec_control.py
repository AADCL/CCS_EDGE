"""Wheeltec manual/autonomous authority coordinator."""
from __future__ import absolute_import

import json
import os
import threading
import time


def localized_state_available(path):
    try:
        with open(os.path.abspath(os.path.expanduser(path)), "r") as stream:
            value = json.load(stream)
    except (IOError, OSError, TypeError, ValueError):
        return False
    return (
        isinstance(value, dict)
        and value.get("schema_version") == 2
        and value.get("status") == "localized"
        and isinstance(value.get("map_id"), str)
        and bool(value["map_id"].strip())
    )


def localization_is_healthy(state_available, odom_received_at, now, timeout):
    return (
        bool(state_available)
        and float(odom_received_at) > 0.0
        and 0.0 <= float(now) - float(odom_received_at) <= float(timeout)
    )


class WheeltecControlAuthority(object):
    def __init__(self, rospy, config):
        self.rospy = rospy
        self.config = config
        self.lock = threading.RLock()
        self.transition_lock = threading.Lock()
        self.odom_received_at = 0.0
        self.desired_enabled = False
        self.driver_enabled = False
        self.driver_received_at = 0.0
        self.enabled_pub = None
        self.localization_pub = None

    def _safety_enabled(self):
        return self.config.get("safety_gate_enabled", True)

    def start(self):
        from nav_msgs.msg import Odometry
        from std_msgs.msg import Bool
        from std_srvs.srv import SetBool, Trigger

        self.driver_enable = self.rospy.ServiceProxy(
            self.config["driver_enable_service"], SetBool)
        self.driver_stop = self.rospy.ServiceProxy(
            self.config["driver_stop_service"], Trigger)
        self.driver_reset = self.rospy.ServiceProxy(
            self.config["driver_reset_service"], Trigger)
        self.safety_arm = self.safety_stop = self.safety_reset = None
        if self._safety_enabled():
            self.safety_arm = self.rospy.ServiceProxy(
                self.config["safety_arm_service"], Trigger)
            self.safety_stop = self.rospy.ServiceProxy(
                self.config["safety_stop_service"], Trigger)
            self.safety_reset = self.rospy.ServiceProxy(
                self.config["safety_reset_service"], Trigger)
        self.enabled_pub = self.rospy.Publisher(
            self.config["enabled_topic"], Bool, queue_size=1, latch=True)
        self.localization_pub = self.rospy.Publisher(
            self.config["localization_ok_topic"], Bool, queue_size=1, latch=True)
        self.rospy.Subscriber(
            self.config["odom_topic"], Odometry, self._odom_callback, queue_size=1)
        self.rospy.Subscriber(
            self.config["driver_enabled_topic"], Bool,
            self._driver_enabled_callback, queue_size=1)
        if self.config.get("driver_auto_acquire", False):
            self.rospy.Subscriber(self.config["driver_odom_topic"], Odometry, self._driver_odom_callback, queue_size=1)
        self.rospy.Service("~enable", SetBool, self._enable_callback)
        self.rospy.Service("~stop", Trigger, self._stop_callback)
        self.rospy.Service("~reset", Trigger, self._reset_callback)
        period = 1.0 / float(self.config.get("state_publish_hz", 10.0))
        self.rospy.Timer(self.rospy.Duration(period), self._publish_state)
        self._publish_state()

    def _odom_callback(self, unused_message):
        with self.lock:
            self.odom_received_at = time.monotonic()

    def _driver_enabled_callback(self, message):
        with self.lock:
            self.driver_enabled = bool(message.data)
        self._publish_state()

    def _driver_odom_callback(self, message):
        age = self.rospy.Time.now().to_sec() - message.header.stamp.to_sec()
        if message.header.stamp.to_sec() > 0 and -0.2 <= age <= 1.0:
            with self.lock:
                self.driver_received_at = time.monotonic()

    def _localized(self):
        with self.lock:
            received_at = self.odom_received_at
        return localization_is_healthy(
            localized_state_available(self.config["state_file"]),
            received_at, time.monotonic(),
            self.config.get("odom_timeout_seconds", 1.0))

    def _publish_state(self, unused_event=None):
        from std_msgs.msg import Bool
        localized = self._localized()
        with self.lock:
            # V6 returns manual authority during an idle command interval.
            # A fresh command can reacquire it after the coordinator enables a task.
            if self.config.get("driver_auto_acquire", False):
                driver_available = 0 <= time.monotonic() - self.driver_received_at <= 1.0 and self.driver_received_at > 0
                enabled = self.desired_enabled and localized and driver_available
            else:
                enabled = self.desired_enabled and self.driver_enabled
        if self.localization_pub is not None:
            self.localization_pub.publish(Bool(data=localized))
        if self.enabled_pub is not None:
            self.enabled_pub.publish(Bool(data=enabled))

    @staticmethod
    def _require(response, action):
        if not getattr(response, "success", False):
            raise ValueError(
                "%s refused: %s" % (
                    action, getattr(response, "message", "no response")))

    def _enable_callback(self, request):
        from std_srvs.srv import SetBoolResponse
        if not self.transition_lock.acquire(False):
            return SetBoolResponse(success=False, message="control transition is active")
        try:
            if not request.data:
                warning = self._normal_release()
                message = "manual controller authority restored"
                if warning:
                    message += "; safety gate was unavailable: %s" % warning
                return SetBoolResponse(
                    success=True, message=message)
            if not self._localized():
                return SetBoolResponse(
                    success=False, message="localization is unavailable or stale")
            if self._safety_enabled():
                self._require(self.safety_reset(), "safety reset")
            with self.lock:
                self.desired_enabled = True
            self._require(self.driver_enable(True), "driver autonomous enable")
            if self._safety_enabled():
                self._require(self.safety_arm(), "safety arm")
            self._publish_state()
            return SetBoolResponse(
                success=True, message="autonomous controller authority acquired")
        except Exception as exc:
            for client in ((self.safety_stop, self.driver_stop) if self._safety_enabled()
                           else (self.driver_stop,)):
                try:
                    client()
                except Exception:
                    pass
            with self.lock:
                self.desired_enabled = False
            self._publish_state()
            return SetBoolResponse(success=False, message=str(exc))
        finally:
            self.transition_lock.release()

    def _normal_release(self):
        safety_error = ""
        if self._safety_enabled():
            try:
                self._require(self.safety_stop(), "safety stop")
            except Exception as exc:
                safety_error = str(exc)
        try:
            self._require(self.driver_enable(False), "driver manual release")
        except Exception as exc:
            raise ValueError(
                "; ".join(value for value in (safety_error, str(exc)) if value))
        with self.lock:
            self.desired_enabled = False
        self._publish_state()
        return safety_error

    def _stop_callback(self, unused_request):
        from std_srvs.srv import TriggerResponse
        if not self.transition_lock.acquire(False):
            return TriggerResponse(success=False, message="control transition is active")
        try:
            errors = []
            stops = [("driver stop", self.driver_stop)]
            if self._safety_enabled():
                stops.insert(0, ("safety stop", self.safety_stop))
            for action, client in stops:
                try:
                    self._require(client(), action)
                except Exception as exc:
                    errors.append(str(exc))
            with self.lock:
                self.desired_enabled = False
            self._publish_state()
            return TriggerResponse(
                success=not errors,
                message="fault stop latched" if not errors else "; ".join(errors))
        finally:
            self.transition_lock.release()

    def _reset_callback(self, unused_request):
        from std_srvs.srv import TriggerResponse
        if not self.transition_lock.acquire(False):
            return TriggerResponse(success=False, message="control transition is active")
        try:
            self._require(self.driver_reset(), "driver authority reset")
            safety_warning = ""
            if self._safety_enabled():
                try:
                    self._require(self.safety_reset(), "safety reset")
                except Exception as exc:
                    safety_warning = str(exc)
            with self.lock:
                self.desired_enabled = False
            self._publish_state()
            message = "fault reset; manual authority restored"
            if safety_warning:
                message += "; safety gate was unavailable: %s" % safety_warning
            return TriggerResponse(
                success=True, message=message)
        except Exception as exc:
            return TriggerResponse(success=False, message=str(exc))
        finally:
            self.transition_lock.release()
