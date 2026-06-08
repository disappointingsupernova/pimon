"""Systemd watchdog integration for PiMon.

Sends sd_notify WATCHDOG=1 pings to systemd so the service is
automatically restarted if the poll loop stalls.
"""

import logging
import os
import socket

logger = logging.getLogger("pimon")

_notify_socket: socket.socket | None = None
_enabled: bool = False


def init_watchdog() -> None:
    """Initialise the systemd notify socket if WatchdogSec is configured."""
    global _notify_socket, _enabled

    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return

    _notify_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    _notify_socket.connect(addr)
    _enabled = True
    logger.info("Systemd watchdog enabled")


def notify_ready() -> None:
    """Notify systemd that the service has finished starting."""
    _send(b"READY=1")


def notify_watchdog() -> None:
    """Send a watchdog keepalive ping to systemd."""
    _send(b"WATCHDOG=1")


def notify_stopping() -> None:
    """Notify systemd that the service is stopping."""
    _send(b"STOPPING=1")


def _send(msg: bytes) -> None:
    """Send a message to the systemd notify socket."""
    if _enabled and _notify_socket:
        try:
            _notify_socket.sendall(msg)
        except OSError:
            pass
