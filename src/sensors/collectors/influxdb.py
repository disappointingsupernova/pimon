"""InfluxDB statistics collector.

Auto-detects InfluxDB by querying its health endpoint at localhost:8086.

Metrics collected:
    - Health status
    - Version
    - Uptime
"""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("pi_temp_alerter")

_HEALTH_URL = "http://127.0.0.1:8086/health"


def collect_influxdb_stats() -> dict | None:
    """Collect statistics from InfluxDB's health endpoint.

    Returns a dict of metrics, or None if InfluxDB is unavailable.
    """
    try:
        req = urllib.request.Request(_HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        return {
            "status": data.get("status", "unknown"),
            "version": data.get("version", "unknown"),
            "message": data.get("message", ""),
        }
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None
