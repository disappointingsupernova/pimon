"""Unbound DNS resolver statistics collector.

Auto-detects Unbound by running 'unbound-control stats_noreset'.

Metrics collected:
    - Total queries
    - Cache hits/misses
    - Cache hit ratio
    - Recursion average time
    - Current cache size
"""

import logging
import subprocess

logger = logging.getLogger("pimon")


def collect_unbound_stats() -> dict | None:
    """Collect statistics from Unbound via unbound-control.

    Returns a dict of metrics, or None if Unbound is unavailable.
    """
    try:
        result = subprocess.run(
            ["unbound-control", "stats_noreset"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        stats = {}
        for line in result.stdout.strip().split("\n"):
            if "=" in line:
                key, val = line.split("=", 1)
                stats[key.strip()] = val.strip()

        total = int(float(stats.get("total.num.queries", 0)))
        cache_hits = int(float(stats.get("total.num.cachehits", 0)))
        cache_misses = int(float(stats.get("total.num.cachemiss", 0)))
        hit_ratio = (cache_hits / total * 100) if total > 0 else 0.0

        return {
            "total_queries": total,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_hit_ratio": round(hit_ratio, 1),
            "recursion_avg_ms": round(float(stats.get("total.recursion.time.avg", 0)) * 1000, 2),
            "num_rrsets": int(float(stats.get("msg.cache.count", 0))),
        }
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None
