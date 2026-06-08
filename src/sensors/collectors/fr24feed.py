"""FlightRadar24 feed (fr24feed) statistics collector.

Gathers statistics from the fr24feed service by parsing its status
output or reading from its local HTTP status endpoint.

Metrics collected:
    - Feed connection status (connected/disconnected)
    - Aircraft tracked
    - Aircraft uploaded
    - Feed mode (MLAT/no MLAT)
    - Receiver connected status
    - Link type
"""

import json
import logging
import subprocess
import urllib.request
import urllib.error

from src.config import config

logger = logging.getLogger("pi_temp_alerter")

# fr24feed exposes stats on a local HTTP endpoint
_FR24_STATUS_URL = "http://127.0.0.1:8754/monitor.json"


def collect_fr24_stats() -> dict | None:
    """Collect statistics from the fr24feed service.

    Attempts to read from the fr24feed HTTP monitor endpoint first,
    falls back to parsing 'fr24feed-status' command output.

    Returns a dict of metrics, or None if the service is unavailable.
    """
    if not config.collector_fr24_enabled:
        return None

    # Try the HTTP monitor endpoint first (more reliable)
    stats = _collect_from_http()
    if stats:
        return stats

    # Fall back to CLI status command
    return _collect_from_cli()


def _collect_from_http() -> dict | None:
    """Read fr24feed stats from its local HTTP monitor endpoint."""
    try:
        req = urllib.request.Request(_FR24_STATUS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        return {
            "feed_connected": bool(data.get("feed_status", 0)),
            "feed_alias": data.get("feed_alias", ""),
            "aircraft_tracked": data.get("d11_map_size", 0),
            "aircraft_uploaded": data.get("feed_num_ac_tracked", 0),
            "feed_connection_type": data.get("feed_current_mode", "unknown"),
            "receiver_connected": bool(data.get("rx_connected", 0)),
            "mlat_enabled": bool(data.get("mlat_timestamp_mismatch", -1) != -1),
            "build_version": data.get("build_version", "unknown"),
        }
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
        return None


def _collect_from_cli() -> dict | None:
    """Parse fr24feed-status command output as a fallback."""
    try:
        result = subprocess.run(
            ["fr24feed-status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        output = result.stdout
        stats = {
            "feed_connected": "is connected" in output.lower(),
            "receiver_connected": "receiver" in output.lower() and "connected" in output.lower(),
            "aircraft_tracked": 0,
            "aircraft_uploaded": 0,
        }

        # Try to parse aircraft counts from output lines
        for line in output.split("\n"):
            if "ac" in line.lower() and "tracked" in line.lower():
                parts = line.split()
                for part in parts:
                    if part.isdigit():
                        stats["aircraft_tracked"] = int(part)
                        break

        return stats
    except (OSError, subprocess.SubprocessError):
        return None
