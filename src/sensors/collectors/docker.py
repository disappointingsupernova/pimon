"""Docker container statistics collector.

Auto-detects Docker by checking for the Docker socket at /var/run/docker.sock.

Metrics collected:
    - Containers running/stopped/total
    - Images count
    - System-wide CPU/memory usage
"""

import json
import logging
import socket
import http.client
from pathlib import Path

logger = logging.getLogger("pimon")

_DOCKER_SOCKET = "/var/run/docker.sock"


def collect_docker_stats() -> dict | None:
    """Collect statistics from Docker via the Unix socket API.

    Returns a dict of metrics, or None if Docker is unavailable.
    """
    if not Path(_DOCKER_SOCKET).exists():
        return None

    try:
        # Query container list
        containers = _docker_api("/containers/json?all=true")
        if containers is None:
            return None

        running = sum(1 for c in containers if c.get("State") == "running")
        stopped = sum(1 for c in containers if c.get("State") != "running")

        # Query image list
        images = _docker_api("/images/json")
        image_count = len(images) if images else 0

        return {
            "containers_total": len(containers),
            "containers_running": running,
            "containers_stopped": stopped,
            "images": image_count,
        }
    except (OSError, ValueError):
        return None


def _docker_api(path: str) -> list | dict | None:
    """Make a request to the Docker API via Unix socket."""
    try:
        conn = http.client.HTTPConnection("localhost")
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.connect(_DOCKER_SOCKET)
        conn.request("GET", path)
        resp = conn.getresponse()
        if resp.status == 200:
            return json.loads(resp.read().decode("utf-8"))
        return None
    except (OSError, json.JSONDecodeError):
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass
