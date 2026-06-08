"""GPS (gpsd) statistics collector.

Auto-detects by connecting to gpsd at localhost:2947.

Metrics collected:
    - Fix type (no fix, 2D, 3D)
    - Latitude/longitude
    - Altitude
    - Speed
    - Satellites visible/used
    - HDOP/VDOP
    - Time accuracy
"""

import json
import logging
import socket

logger = logging.getLogger("pi_temp_alerter")

_GPSD_HOST = "127.0.0.1"
_GPSD_PORT = 2947


def collect_gps_stats() -> dict | None:
    """Collect GPS statistics from gpsd.

    Connects to gpsd, requests a poll, and parses the TPV and SKY reports.

    Returns a dict of metrics, or None if gpsd is unavailable.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((_GPSD_HOST, _GPSD_PORT))

        # gpsd sends a version line on connect, then we request a poll
        _recv_line(sock)  # Read version banner
        sock.sendall(b'?POLL;\n')

        # Read the POLL response
        response = _recv_line(sock)
        sock.close()

        if not response:
            return None

        data = json.loads(response)
        if data.get("class") != "POLL":
            return None

        result = {
            "fix_type": 0,
            "latitude": 0.0,
            "longitude": 0.0,
            "altitude_m": 0.0,
            "speed_kmh": 0.0,
            "satellites_visible": 0,
            "satellites_used": 0,
            "hdop": 99.9,
        }

        # Parse TPV (Time-Position-Velocity) report
        tpv_list = data.get("tpv", [])
        if tpv_list:
            tpv = tpv_list[0]
            result["fix_type"] = tpv.get("mode", 0)
            result["latitude"] = round(tpv.get("lat", 0.0), 6)
            result["longitude"] = round(tpv.get("lon", 0.0), 6)
            result["altitude_m"] = round(tpv.get("alt", 0.0), 1)
            # Speed from m/s to km/h
            result["speed_kmh"] = round(tpv.get("speed", 0.0) * 3.6, 1)

        # Parse SKY report for satellite info
        sky_list = data.get("sky", [])
        if sky_list:
            sky = sky_list[0]
            result["hdop"] = round(sky.get("hdop", 99.9), 1)
            sats = sky.get("satellites", [])
            result["satellites_visible"] = len(sats)
            result["satellites_used"] = sum(1 for s in sats if s.get("used", False))

        return result
    except (OSError, json.JSONDecodeError, ValueError, IndexError):
        return None


def _recv_line(sock: socket.socket) -> str:
    """Read a single line from the gpsd socket."""
    buf = b""
    while True:
        chunk = sock.recv(1)
        if not chunk or chunk == b"\n":
            break
        buf += chunk
    return buf.decode("utf-8", errors="replace").strip()
