"""Systemd service status collector.

Reports running/failed state for a configurable list of services.
Auto-detects by checking if systemctl is available.

Metrics collected:
    - Per-service: active/inactive/failed state
    - Total services monitored
    - Count of failed services
"""

import logging
import os
import subprocess

logger = logging.getLogger("pi_temp_alerter")


def collect_systemd_stats() -> dict | None:
    """Collect status of monitored systemd services.

    Set SYSTEMD_MONITOR_SERVICES in .env as a comma-separated list
    of service names to monitor. If not set, returns None.

    Returns a dict of metrics, or None if systemctl is unavailable
    or no services are configured.
    """
    services_raw = os.getenv("SYSTEMD_MONITOR_SERVICES", "")
    if not services_raw:
        return None

    services = [s.strip() for s in services_raw.split(",") if s.strip()]
    if not services:
        return None

    try:
        # Check systemctl is available
        result = subprocess.run(
            ["systemctl", "--version"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
    except (OSError, subprocess.SubprocessError):
        return None

    statuses = {}
    failed_count = 0

    for service in services:
        state = _get_service_state(service)
        statuses[service] = state
        if state == "failed":
            failed_count += 1

    return {
        "services_monitored": len(services),
        "services_running": sum(1 for s in statuses.values() if s == "active"),
        "services_failed": failed_count,
        "services": statuses,
    }


def _get_service_state(service: str) -> str:
    """Get the active state of a systemd service."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
