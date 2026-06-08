"""Tailscale mesh VPN statistics collector.

Auto-detects Tailscale by running 'tailscale status --json'.

Metrics collected:
    - Total peers
    - Online/offline peer counts
    - This node's tailnet name
"""

import json
import logging
import subprocess

logger = logging.getLogger("pi_temp_alerter")


def collect_tailscale_stats() -> dict | None:
    """Collect statistics from Tailscale via 'tailscale status --json'.

    Returns a dict of metrics, or None if Tailscale is unavailable.
    """
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        peers = data.get("Peer", {})

        online = sum(1 for p in peers.values() if p.get("Online", False))
        total = len(peers)

        return {
            "peers_total": total,
            "peers_online": online,
            "peers_offline": total - online,
            "tailnet_name": data.get("MagicDNSSuffix", "unknown"),
            "self_online": data.get("Self", {}).get("Online", False),
        }
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None
