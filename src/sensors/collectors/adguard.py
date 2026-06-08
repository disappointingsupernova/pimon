"""AdGuard Home DNS ad blocker statistics collector.

Auto-detects AdGuard Home by querying its HTTP API at localhost:3000.

Metrics collected:
    - DNS queries today
    - Blocked queries
    - Block percentage
    - Average processing time
    - Rules count
"""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("pi_temp_alerter")

_STATS_URL = "http://127.0.0.1:3000/control/stats"


def collect_adguard_stats() -> dict | None:
    """Collect statistics from AdGuard Home's HTTP API.

    Returns a dict of metrics, or None if AdGuard Home is unavailable.
    """
    try:
        req = urllib.request.Request(_STATS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        total = data.get("num_dns_queries", 0)
        blocked = data.get("num_blocked_filtering", 0)
        percent = (blocked / total * 100) if total > 0 else 0.0

        return {
            "dns_queries_today": total,
            "blocked_today": blocked,
            "block_percentage": round(percent, 1),
            "avg_processing_time_ms": round(data.get("avg_processing_time", 0) * 1000, 1),
            "rules_count": data.get("num_replaced_safebrowsing", 0) + data.get("num_replaced_parental", 0),
            "safebrowsing_blocked": data.get("num_replaced_safebrowsing", 0),
            "parental_blocked": data.get("num_replaced_parental", 0),
        }
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
