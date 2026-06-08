"""dump1090-fa ADS-B decoder statistics collector.

Auto-detects dump1090-fa by querying its HTTP stats endpoint.

Metrics collected:
    - Aircraft tracked
    - Messages received
    - Signal strength
    - Tracks with position
"""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("pi_temp_alerter")

_STATS_URL = "http://127.0.0.1:8080/data/stats.json"
_AIRCRAFT_URL = "http://127.0.0.1:8080/data/aircraft.json"


def collect_dump1090_stats() -> dict | None:
    """Collect statistics from dump1090-fa's HTTP endpoint.

    Returns a dict of metrics, or None if dump1090-fa is unavailable.
    """
    try:
        # Get stats
        req = urllib.request.Request(_STATS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            stats = json.loads(resp.read().decode("utf-8"))

        last1min = stats.get("last1min", {})
        local = last1min.get("local", {})

        result = {
            "messages_rate": round(local.get("messages", 0) / max(local.get("seconds", 1), 1), 1),
            "signal_mean_dbfs": round(local.get("signal", 0), 1),
            "signal_peak_dbfs": round(local.get("peak_signal", 0), 1),
            "noise_dbfs": round(local.get("noise", 0), 1),
            "tracks_with_position": last1min.get("cpr", {}).get("global_ok", 0),
        }

        # Get aircraft count
        req = urllib.request.Request(_AIRCRAFT_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            aircraft = json.loads(resp.read().decode("utf-8"))

        ac_list = aircraft.get("aircraft", [])
        result["aircraft_total"] = len(ac_list)
        result["aircraft_with_position"] = sum(1 for a in ac_list if "lat" in a)

        return result
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
