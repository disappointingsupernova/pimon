"""Zigbee2MQTT statistics collector.

Auto-detects Zigbee2MQTT by querying its HTTP API at localhost:8080.

Metrics collected:
    - Devices paired
    - Coordinator type
    - Permit join status
    - Log level
"""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("pi_temp_alerter")

_BRIDGE_URL = "http://127.0.0.1:8080/api/bridge/info"
_DEVICES_URL = "http://127.0.0.1:8080/api/devices"


def collect_zigbee2mqtt_stats() -> dict | None:
    """Collect statistics from Zigbee2MQTT's HTTP API.

    Returns a dict of metrics, or None if Zigbee2MQTT is unavailable.
    """
    try:
        # Get bridge info
        req = urllib.request.Request(_BRIDGE_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            bridge = json.loads(resp.read().decode("utf-8"))

        # Get devices list
        req = urllib.request.Request(_DEVICES_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            devices = json.loads(resp.read().decode("utf-8"))

        coordinator = bridge.get("coordinator", {})
        return {
            "devices_total": len(devices),
            "devices_available": sum(1 for d in devices if not d.get("disabled", False)),
            "coordinator_type": coordinator.get("type", "unknown"),
            "permit_join": bridge.get("permit_join", False),
            "version": bridge.get("version", "unknown"),
        }
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
