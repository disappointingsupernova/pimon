"""Pi-hole DNS ad blocker statistics collector.

Auto-detects Pi-hole by querying its local HTTP API at localhost/admin/api.php.

Metrics collected:
    - DNS queries today
    - Ads blocked today
    - Block percentage
    - Domains on blocklist
    - Unique clients
    - DNS query types breakdown
"""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("pimon")

_API_URL = "http://127.0.0.1/admin/api.php?summary"


def collect_pihole_stats() -> dict | None:
    """Collect statistics from Pi-hole's HTTP API.

    Returns a dict of metrics, or None if Pi-hole is unavailable.
    """
    try:
        req = urllib.request.Request(_API_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        return {
            "dns_queries_today": int(data.get("dns_queries_today", 0)),
            "ads_blocked_today": int(data.get("ads_blocked_today", 0)),
            "ads_percentage_today": round(float(data.get("ads_percentage_today", 0)), 1),
            "domains_being_blocked": int(data.get("domains_being_blocked", 0)),
            "unique_clients": int(data.get("unique_clients", 0)),
            "queries_cached": int(data.get("queries_cached", 0)),
            "queries_forwarded": int(data.get("queries_forwarded", 0)),
            "status": data.get("status", "unknown"),
        }
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
