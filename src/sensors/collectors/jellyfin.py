"""Jellyfin Media Server statistics collector.

Auto-detects Jellyfin by querying its local HTTP API at localhost:8096.

Metrics collected:
    - Active sessions
    - Users currently streaming
    - Server version
"""

import json
import logging
import urllib.request
import urllib.error
import os

logger = logging.getLogger("pimon")

_BASE_URL = "http://127.0.0.1:8096"


def collect_jellyfin_stats() -> dict | None:
    """Collect statistics from Jellyfin's HTTP API.

    Returns a dict of metrics, or None if Jellyfin is unavailable.
    """
    api_key = os.getenv("JELLYFIN_API_KEY", "")

    try:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["X-Emby-Token"] = api_key

        # Check if Jellyfin is running via system info (public endpoint)
        req = urllib.request.Request(
            f"{_BASE_URL}/System/Info/Public",
            headers=headers,
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            info = json.loads(resp.read().decode("utf-8"))

        stats = {
            "version": info.get("Version", "unknown"),
            "server_name": info.get("ServerName", "unknown"),
        }

        # Sessions require an API key
        if api_key:
            req = urllib.request.Request(
                f"{_BASE_URL}/Sessions",
                headers=headers,
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                sessions = json.loads(resp.read().decode("utf-8"))

            active = [s for s in sessions if s.get("NowPlayingItem")]
            stats["active_sessions"] = len(active)
            stats["total_sessions"] = len(sessions)
        else:
            stats["active_sessions"] = -1
            stats["total_sessions"] = -1

        return stats
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
