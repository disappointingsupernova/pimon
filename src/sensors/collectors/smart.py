"""SMART disk health statistics collector.

Auto-detects by running 'smartctl' against common disk devices.

Metrics collected:
    - Overall health status
    - Temperature
    - Power-on hours
    - Reallocated sector count
"""

import logging
import subprocess
import json

logger = logging.getLogger("pimon")

_DEVICES = ["/dev/sda", "/dev/nvme0", "/dev/mmcblk0"]


def collect_smart_stats() -> dict | None:
    """Collect SMART disk health data via smartctl.

    Returns a dict of metrics, or None if smartctl is unavailable.
    """
    for device in _DEVICES:
        stats = _try_device(device)
        if stats:
            return stats
    return None


def _try_device(device: str) -> dict | None:
    """Attempt to read SMART data from a device."""
    try:
        result = subprocess.run(
            ["smartctl", "-a", "--json", device],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # smartctl returns non-zero for various non-fatal conditions
        if not result.stdout:
            return None

        data = json.loads(result.stdout)

        health = data.get("smart_status", {}).get("passed", None)
        temp = data.get("temperature", {}).get("current", 0)
        power_on = data.get("power_on_time", {}).get("hours", 0)

        # Look for reallocated sectors in the attributes table
        reallocated = 0
        for attr in data.get("ata_smart_attributes", {}).get("table", []):
            if attr.get("id") == 5:  # Reallocated Sector Count
                reallocated = attr.get("raw", {}).get("value", 0)
                break

        return {
            "device": device,
            "healthy": health,
            "temperature_c": temp,
            "power_on_hours": power_on,
            "reallocated_sectors": reallocated,
        }
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None
