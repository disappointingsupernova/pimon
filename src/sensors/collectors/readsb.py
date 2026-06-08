"""readsb ADS-B decoder statistics collector.

Gathers statistics from the readsb service by reading its JSON
statistics files from the run directory.

Metrics collected:
    - Aircraft currently tracked
    - Aircraft with position
    - Messages received (total and per second)
    - Signal strength (mean, peak)
    - Tracks (single message, total)
    - CPU usage (demodulation, reader, background)
    - Local/remote clients connected
"""

import json
import logging
from pathlib import Path

from src.config import config

logger = logging.getLogger("pi_temp_alerter")

# Default paths where readsb writes its stats JSON files
_STATS_FILE = Path("/run/readsb/stats.json")
_AIRCRAFT_FILE = Path("/run/readsb/aircraft.json")


def collect_readsb_stats() -> dict | None:
    """Collect statistics from the readsb ADS-B decoder.

    Reads from readsb's JSON stats files at /run/readsb/.

    Returns a dict of metrics, or None if the service is unavailable.
    """
    if not config.collector_readsb_enabled:
        return None

    stats_path = Path(config.collector_readsb_stats_dir) / "stats.json"
    aircraft_path = Path(config.collector_readsb_stats_dir) / "aircraft.json"

    result = {}

    # Read main statistics
    stats = _read_json(stats_path)
    if stats:
        # Last 1-minute statistics
        last1min = stats.get("last1min", {})
        local = last1min.get("local", {})
        remote = last1min.get("remote", {})
        cpr = last1min.get("cpr", {})
        cpu = last1min.get("cpu", {})

        result["messages_rate"] = round(local.get("messages", 0) / max(local.get("seconds", 1), 1), 1)
        result["messages_total"] = stats.get("total", {}).get("local", {}).get("messages", 0)

        # Signal strength
        result["signal_mean_dbfs"] = round(local.get("signal", 0), 1)
        result["signal_peak_dbfs"] = round(local.get("peak_signal", 0), 1)
        result["noise_dbfs"] = round(local.get("noise", 0), 1)

        # Positions and tracks
        result["positions_rate"] = round(cpr.get("global_ok", 0) / max(last1min.get("seconds", 1), 1), 1)
        result["tracks_single_message"] = last1min.get("tracks", {}).get("single_message", 0)
        result["tracks_all"] = last1min.get("tracks", {}).get("all", 0)

        # CPU usage (milliseconds per second)
        result["cpu_demod_ms"] = round(cpu.get("demod", 0), 1)
        result["cpu_reader_ms"] = round(cpu.get("reader", 0), 1)
        result["cpu_background_ms"] = round(cpu.get("background", 0), 1)

        # Clients
        result["local_clients"] = local.get("accepted", [0, 0])
        result["remote_clients"] = remote.get("accepted", [0, 0])

        # Flatten client arrays to single counts
        if isinstance(result["local_clients"], list):
            result["local_clients"] = sum(result["local_clients"])
        if isinstance(result["remote_clients"], list):
            result["remote_clients"] = sum(result["remote_clients"])

    # Read aircraft count
    aircraft = _read_json(aircraft_path)
    if aircraft:
        ac_list = aircraft.get("aircraft", [])
        result["aircraft_total"] = len(ac_list)
        result["aircraft_with_position"] = sum(
            1 for a in ac_list if "lat" in a and "lon" in a
        )
        result["aircraft_with_mlat"] = sum(
            1 for a in ac_list if a.get("mlat", [])
        )
    else:
        result["aircraft_total"] = 0
        result["aircraft_with_position"] = 0
        result["aircraft_with_mlat"] = 0

    return result if result else None


def _read_json(path: Path) -> dict | None:
    """Read and parse a JSON file, returning None on any failure."""
    try:
        if not path.exists():
            return None
        content = path.read_text()
        return json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to read %s: %s", path, exc)
        return None
