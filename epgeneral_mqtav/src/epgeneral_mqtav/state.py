"""Python 3.6 compatible, thread-safe generic health snapshots."""

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
import uuid

from .fields import boolean, number


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_percentage(value, unit="legacy_auto"):
    """Normalize explicitly configured units; legacy_auto preserves old profiles."""
    numeric = number(value)
    if numeric is None or numeric < 0:
        return None
    if unit == "fraction" or (unit == "legacy_auto" and numeric <= 1):
        numeric *= 100
    if unit != "legacy_auto" and numeric > 100:
        return None
    return round(min(numeric, 100.0), 2)


class HealthState(object):
    def __init__(self, device):
        self._device = device
        self._lock = Lock()
        self._sequence = 0
        self._session_id = uuid.uuid4().hex
        self._health = {
            "fcu_connected": None,
            "armed": None,
            "system_status": None,
            "flight_mode": "unknown",
            "battery": {"percentage": None, "voltage": None, "current": None},
            "mission_status": "unknown",
        }

    def update_state(self, connected, armed, system_status, mode, preserve_connected=False):
        optional_bool = boolean
        status = number(system_status)
        if status is not None and status.is_integer():
            status = int(status)

        with self._lock:
            self._health.update(
                armed=optional_bool(armed),
                system_status=status,
                flight_mode=str(mode) if mode else "unknown",
            )
            if not preserve_connected:
                self._health["fcu_connected"] = optional_bool(connected)

    def update_connected(self, connected):
        with self._lock:
            self._health["fcu_connected"] = boolean(connected)

    def update_battery(self, percentage, voltage, current, percentage_unit="legacy_auto"):
        def rounded(value):
            value = number(value)
            return round(value, 3) if value is not None else None

        with self._lock:
            self._health["battery"] = {
                "percentage": normalize_percentage(percentage, percentage_unit),
                "voltage": rounded(voltage),
                "current": rounded(current),
            }

    def update_mission(self, status):
        with self._lock:
            self._health["mission_status"] = "unknown" if status is None or str(status) == "" else str(status)

    def payload(self, message_type):
        with self._lock:
            self._sequence += 1
            return {
                "schema_version": "1.0",
                "message_type": message_type,
                "timestamp": utc_timestamp(),
                "sequence": self._sequence,
                "session_id": self._session_id,
                "device": {"id": self._device.device_id, "ip": self._device.ip_address},
                "health": deepcopy(self._health),
            }

    def presence_payload(self, status):
        return {
            "schema_version": "1.0",
            "message_type": "presence",
            "timestamp": utc_timestamp(),
            "session_id": self._session_id,
            "device": {"id": self._device.device_id, "ip": self._device.ip_address},
            "status": status,
        }
