"""WireGuard VPN statistics collector.

Auto-detects WireGuard by running 'wg show' (requires root or cap_net_admin).

Metrics collected:
    - Number of peers
    - Total bytes received/transmitted
    - Peers with recent handshake (active)
"""

import logging
import subprocess
import time

logger = logging.getLogger("pi_temp_alerter")


def collect_wireguard_stats() -> dict | None:
    """Collect statistics from WireGuard via 'wg show'.

    Returns a dict of metrics, or None if WireGuard is unavailable.
    """
    try:
        result = subprocess.run(
            ["wg", "show", "all", "dump"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if not lines:
            return None

        peers = 0
        active_peers = 0
        total_rx = 0
        total_tx = 0
        now = time.time()

        for line in lines[1:]:  # Skip interface line
            parts = line.split("\t")
            if len(parts) >= 6:
                peers += 1
                total_rx += int(parts[5]) if parts[5] else 0
                total_tx += int(parts[6]) if parts[6] else 0
                # Handshake within last 3 minutes = active
                last_handshake = int(parts[4]) if parts[4] and parts[4] != "0" else 0
                if last_handshake > 0 and (now - last_handshake) < 180:
                    active_peers += 1

        return {
            "peers_total": peers,
            "peers_active": active_peers,
            "bytes_received": total_rx,
            "bytes_transmitted": total_tx,
            "rx_mb": round(total_rx / (1024 * 1024), 1),
            "tx_mb": round(total_tx / (1024 * 1024), 1),
        }
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
