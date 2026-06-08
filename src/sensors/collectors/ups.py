"""UPS (Network UPS Tools / NUT) statistics collector.

Auto-detects a UPS by running 'upsc' against the default UPS name.

Metrics collected:
    - Battery charge percentage
    - Battery runtime remaining
    - Input voltage
    - Load percentage
    - UPS status
"""

import logging
import subprocess
import os

logger = logging.getLogger("pi_temp_alerter")


def collect_ups_stats() -> dict | None:
    """Collect statistics from NUT via 'upsc'.

    Returns a dict of metrics, or None if NUT/UPS is unavailable.
    """
    ups_name = os.getenv("UPS_NAME", "ups")

    try:
        result = subprocess.run(
            ["upsc", ups_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        data = {}
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                data[key.strip()] = val.strip()

        return {
            "battery_charge": float(data.get("battery.charge", 0)),
            "battery_runtime_sec": int(float(data.get("battery.runtime", 0))),
            "input_voltage": float(data.get("input.voltage", 0)),
            "output_voltage": float(data.get("output.voltage", 0)),
            "load_percent": float(data.get("ups.load", 0)),
            "status": data.get("ups.status", "unknown"),
        }
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None
