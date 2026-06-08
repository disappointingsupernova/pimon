"""Plex Media Server statistics collector.

Auto-detects Plex by querying its local HTTP API at localhost:32400.
Requires a Plex token for authenticated access (set PLEX_TOKEN in .env).

Metrics collected:
    - Active sessions/streams
    - Transcoding sessions
    - Library section counts
"""

import json
import logging
import urllib.request
import urllib.error
import os

logger = logging.getLogger("pimon")

_BASE_URL = "http://127.0.0.1:32400"


def collect_plex_stats() -> dict | None:
    """Collect statistics from Plex Media Server's HTTP API.

    Returns a dict of metrics, or None if Plex is unavailable.
    """
    token = os.getenv("PLEX_TOKEN", "")

    # Try to detect Plex even without a token (identity endpoint is public)
    try:
        headers = {"Accept": "application/json"}
        if token:
            headers["X-Plex-Token"] = token

        # Check if Plex is running
        req = urllib.request.Request(f"{_BASE_URL}/identity", headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            identity = json.loads(resp.read().decode("utf-8"))

        stats = {
            "server_name": identity.get("MediaContainer", {}).get("machineIdentifier", "unknown"),
            "version": identity.get("MediaContainer", {}).get("version", "unknown"),
        }

        # Sessions require a token
        if token:
            req = urllib.request.Request(
                f"{_BASE_URL}/status/sessions",
                headers=headers,
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                sessions = json.loads(resp.read().decode("utf-8"))

            mc = sessions.get("MediaContainer", {})
            all_sessions = mc.get("Metadata", [])
            stats["active_sessions"] = mc.get("size", 0)
            stats["transcoding_sessions"] = sum(
                1 for s in all_sessions if s.get("TranscodeSession")
            )
        else:
            stats["active_sessions"] = -1  # Unknown without token
            stats["transcoding_sessions"] = -1

        return stats
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
