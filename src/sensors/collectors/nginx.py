"""Nginx web server statistics collector.

Auto-detects Nginx by querying its stub_status endpoint.
Requires 'stub_status' to be enabled in Nginx config.

Metrics collected:
    - Active connections
    - Total accepted/handled connections
    - Total requests
    - Reading/writing/waiting connections
"""

import logging
import urllib.request
import urllib.error

logger = logging.getLogger("pi_temp_alerter")

# Common locations for stub_status
_STATUS_URLS = [
    "http://127.0.0.1/nginx_status",
    "http://127.0.0.1:8080/nginx_status",
    "http://127.0.0.1/status",
]


def collect_nginx_stats() -> dict | None:
    """Collect statistics from Nginx's stub_status endpoint.

    Returns a dict of metrics, or None if Nginx is unavailable.
    """
    for url in _STATUS_URLS:
        stats = _try_endpoint(url)
        if stats:
            return stats
    return None


def _try_endpoint(url: str) -> dict | None:
    """Attempt to parse Nginx stub_status from a URL."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            content = resp.read().decode("utf-8")

        # Parse stub_status format:
        # Active connections: 1
        # server accepts handled requests
        #  5 5 23
        # Reading: 0 Writing: 1 Waiting: 0
        lines = content.strip().split("\n")

        active = int(lines[0].split(":")[1].strip())
        counts = lines[2].split()
        accepts = int(counts[0])
        handled = int(counts[1])
        requests = int(counts[2])

        rw_parts = lines[3].split()
        reading = int(rw_parts[1])
        writing = int(rw_parts[3])
        waiting = int(rw_parts[5])

        return {
            "active_connections": active,
            "accepts": accepts,
            "handled": handled,
            "requests": requests,
            "reading": reading,
            "writing": writing,
            "waiting": waiting,
        }
    except (urllib.error.URLError, OSError, ValueError, IndexError):
        return None
