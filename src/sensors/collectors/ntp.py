"""NTP/chrony time synchronisation statistics collector.

Auto-detects by trying chronyc (chrony) then ntpq (ntpd).

Metrics collected:
    - Synchronisation status
    - Stratum
    - Current offset (ms)
    - Root delay (ms)
    - Reference source
"""

import logging
import subprocess

logger = logging.getLogger("pimon")


def collect_ntp_stats() -> dict | None:
    """Collect NTP synchronisation stats from chrony or ntpd.

    Returns a dict of metrics, or None if neither is available.
    """
    # Try chrony first (more common on modern Debian/Raspberry Pi OS)
    stats = _collect_chrony()
    if stats:
        return stats

    # Fall back to ntpq
    return _collect_ntpq()


def _collect_chrony() -> dict | None:
    """Collect from chronyc tracking."""
    try:
        result = subprocess.run(
            ["chronyc", "tracking"],
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

        # Parse offset (e.g. "+0.000123 seconds" or "-0.000456 seconds")
        offset_str = data.get("Last offset", "0 seconds")
        offset_sec = float(offset_str.split()[0])
        offset_ms = offset_sec * 1000

        # Parse root delay
        delay_str = data.get("Root delay", "0 seconds")
        delay_sec = float(delay_str.split()[0])
        delay_ms = delay_sec * 1000

        return {
            "source": "chrony",
            "reference": data.get("Reference ID", "unknown"),
            "stratum": int(data.get("Stratum", 0)),
            "offset_ms": round(offset_ms, 3),
            "root_delay_ms": round(delay_ms, 3),
            "synchronised": "Normal" in data.get("Leap status", ""),
        }
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _collect_ntpq() -> dict | None:
    """Collect from ntpq -p."""
    try:
        result = subprocess.run(
            ["ntpq", "-pn"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        # Find the active peer (marked with *)
        for line in result.stdout.strip().split("\n"):
            if line.startswith("*"):
                parts = line[1:].split()
                if len(parts) >= 9:
                    return {
                        "source": "ntpd",
                        "reference": parts[0],
                        "stratum": int(parts[2]),
                        "offset_ms": float(parts[8]),
                        "root_delay_ms": float(parts[7]),
                        "synchronised": True,
                    }

        # No active peer found
        return {
            "source": "ntpd",
            "reference": "none",
            "stratum": 16,
            "offset_ms": 0.0,
            "root_delay_ms": 0.0,
            "synchronised": False,
        }
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
