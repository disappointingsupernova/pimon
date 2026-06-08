"""MQTT publisher for PiMon.

Publishes temperature readings, system metrics, alerts, and recovery
events to an MQTT broker. Supports:
    - Home Assistant MQTT auto-discovery (sensors + binary sensors)
    - Last Will and Testament (LWT) for offline detection
    - Command topic subscription for remote control
    - Multi-Pi aggregation (hostname in topic and payload)
    - Grafana-friendly flat payloads with timestamps

Topic structure:
    <prefix>/<hostname>/sensor/<name>/state   - Temperature reading (retained)
    <prefix>/<hostname>/system/state          - System metrics (retained)
    <prefix>/<hostname>/alerts                - Alert events (not retained)
    <prefix>/<hostname>/recovery              - Recovery events (not retained)
    <prefix>/<hostname>/status                - Online/offline (retained, LWT)
    <prefix>/<hostname>/command               - Inbound commands (subscribed)
    homeassistant/sensor/<id>/config          - HA discovery (retained)
    homeassistant/binary_sensor/<id>/config   - HA binary sensor discovery
"""

import json
import logging
import os
import platform
import socket
import subprocess
import time
from datetime import datetime, timezone

from src.config import config

logger = logging.getLogger("pimon")

_client = None
_discovery_sent: set[str] = set()
_hostname = socket.gethostname()
_first_publish_logged: bool = False


def _topic(path: str) -> str:
    """Build a full topic path with prefix and hostname for multi-Pi support."""
    return f"{config.mqtt_topic_prefix}/{_hostname}/{path}"


def _get_client():
    """Lazily initialise the MQTT client with LWT and command subscription."""
    global _client
    if _client is not None:
        return _client

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.warning("paho-mqtt not installed - MQTT publishing disabled")
        return None

    _client = mqtt.Client(client_id=config.mqtt_client_id)

    if config.mqtt_username:
        _client.username_pw_set(config.mqtt_username, config.mqtt_password)

    # Enable TLS encryption if configured
    if config.mqtt_tls:
        import ssl
        _client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)

    # Last Will and Testament: broker publishes "offline" if we disconnect unexpectedly
    _client.will_set(
        _topic("status"),
        payload="offline",
        qos=1,
        retain=True,
    )

    # Set up command handler before connecting
    _client.on_message = _handle_command

    try:
        _client.connect(config.mqtt_host, config.mqtt_port, keepalive=60)
        _client.loop_start()

        # Subscribe to command topic for remote control
        _client.subscribe(_topic("command"), qos=1)
        logger.info(
            "MQTT connected to %s:%d (hostname: %s, LWT enabled)",
            config.mqtt_host, config.mqtt_port, _hostname,
        )
    except (OSError, Exception) as exc:
        logger.error("MQTT connection failed: %s", exc)
        _client = None

    return _client


# =============================================================================
# Command subscription handler
# =============================================================================

def _handle_command(client, userdata, message) -> None:
    """Handle inbound commands from the MQTT command topic.

    Supported commands:
        {"action": "test_alert"}     - Trigger a test alert notification
        {"action": "reload_config"}  - Log a config reload request
        {"action": "status"}         - Publish current status immediately
        {"action": "reboot"}         - Reboot the Pi (requires root)
    """
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        action = payload.get("action", "")
        logger.info("MQTT command received: %s", action)

        if action == "test_alert":
            # Publish a synthetic alert for testing HA automations
            publish_alert("test", "WARNING", 0.0)
            logger.info("Test alert published via MQTT command")

        elif action == "status":
            # Force an immediate status publish
            publish_online()
            logger.info("Status republished via MQTT command")

        elif action == "reboot":
            logger.warning("Reboot requested via MQTT command")
            subprocess.run(["sudo", "reboot"], capture_output=True)

        elif action == "poll_interval":
            # Log the request - actual config change requires .env edit + restart
            new_interval = payload.get("value")
            logger.info(
                "Poll interval change requested to %s (requires .env update and restart)",
                new_interval,
            )

        else:
            logger.warning("Unknown MQTT command action: %s", action)

    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning("Invalid MQTT command payload: %s", exc)


# =============================================================================
# Helpers
# =============================================================================

def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _device_info() -> dict:
    """Return device metadata for Home Assistant discovery."""
    from src import __version__
    return {
        "identifiers": [config.mqtt_client_id],
        "name": f"PiMon ({_hostname})",
        "manufacturer": "Raspberry Pi",
        "model": platform.machine(),
        "sw_version": __version__,
        "configuration_url": f"http://{_hostname}:{config.dashboard_port}",
    }


# =============================================================================
# Home Assistant MQTT Auto-Discovery
# =============================================================================

def _send_ha_discovery(sensor_id: str, name: str, unit: str,
                       state_topic: str, value_template: str,
                       device_class: str | None = None,
                       icon: str | None = None,
                       component: str = "sensor") -> None:
    """Publish a Home Assistant MQTT discovery config message.

    Only sent once per sensor per session to avoid spamming the broker.
    """
    if sensor_id in _discovery_sent:
        return

    client = _get_client()
    if client is None:
        return

    unique_id = f"{config.mqtt_client_id}_{sensor_id}"
    discovery_topic = f"homeassistant/{component}/{unique_id}/config"

    payload = {
        "name": name,
        "unique_id": unique_id,
        "state_topic": state_topic,
        "value_template": value_template,
        "device": _device_info(),
        "availability_topic": _topic("status"),
        "payload_available": "online",
        "payload_not_available": "offline",
    }

    if unit:
        payload["unit_of_measurement"] = unit
    if device_class:
        payload["device_class"] = device_class
    if icon:
        payload["icon"] = icon

    # Binary sensors need payload_on/payload_off
    if component == "binary_sensor":
        payload["payload_on"] = "True"
        payload["payload_off"] = "False"

    client.publish(discovery_topic, json.dumps(payload), qos=1, retain=True)
    _discovery_sent.add(sensor_id)


def publish_ha_discovery_for_sensor(sensor_name: str) -> None:
    """Register a temperature sensor with Home Assistant auto-discovery."""
    state_topic = _topic(f"sensor/{sensor_name}/state")
    _send_ha_discovery(
        sensor_id=f"temp_{sensor_name}",
        name=f"Temperature ({sensor_name})",
        unit="°C",
        state_topic=state_topic,
        value_template="{{ value_json.temperature_c }}",
        device_class="temperature",
    )


def publish_ha_discovery_for_system() -> None:
    """Register system metric sensors with Home Assistant auto-discovery."""
    state_topic = _topic("system/state")

    sensors = [
        ("cpu_percent", "CPU Usage", "%", "{{ value_json.cpu_percent }}", None, "mdi:cpu-64-bit"),
        ("memory_percent", "Memory Usage", "%", "{{ value_json.memory_percent }}", None, "mdi:memory"),
        ("disk_percent", "Disk Usage", "%", "{{ value_json.disk_percent }}", None, "mdi:harddisk"),
        ("cpu_temp", "CPU Temperature", "°C", "{{ value_json.cpu_temp_c }}", "temperature", None),
        ("load_1m", "Load Average (1m)", "", "{{ value_json.load_1m }}", None, "mdi:gauge"),
        ("load_5m", "Load Average (5m)", "", "{{ value_json.load_5m }}", None, "mdi:gauge"),
        ("load_15m", "Load Average (15m)", "", "{{ value_json.load_15m }}", None, "mdi:gauge"),
        ("uptime_hours", "Uptime", "h", "{{ value_json.uptime_hours }}", "duration", "mdi:clock-outline"),
        ("process_count", "Processes", "", "{{ value_json.process_count }}", None, "mdi:format-list-numbered"),
        ("swap_percent", "Swap Usage", "%", "{{ value_json.swap_percent }}", None, "mdi:swap-horizontal"),
        ("network_rx_mb", "Network RX", "MB", "{{ value_json.network_rx_mb }}", "data_size", "mdi:download"),
        ("network_tx_mb", "Network TX", "MB", "{{ value_json.network_tx_mb }}", "data_size", "mdi:upload"),
    ]

    for sensor_id, name, unit, template, device_class, icon in sensors:
        _send_ha_discovery(
            sensor_id=f"sys_{sensor_id}",
            name=name,
            unit=unit,
            state_topic=state_topic,
            value_template=template,
            device_class=device_class,
            icon=icon,
        )

    # Binary sensor for throttle state
    _send_ha_discovery(
        sensor_id="sys_throttled",
        name="Throttled",
        unit="",
        state_topic=state_topic,
        value_template="{{ value_json.throttled }}",
        device_class="problem",
        icon="mdi:alert-circle",
        component="binary_sensor",
    )

    # Binary sensor for alert active state
    _send_ha_discovery(
        sensor_id="alert_active",
        name="Temperature Alert Active",
        unit="",
        state_topic=_topic("alerts"),
        value_template="{{ value_json.level != 'NORMAL' }}",
        device_class="heat",
        icon="mdi:thermometer-alert",
        component="binary_sensor",
    )


# =============================================================================
# Publishing functions
# =============================================================================

def publish_reading(sensor_name: str, temperature: float) -> bool:
    """Publish a sensor temperature reading to MQTT.

    Payload is Grafana-friendly with flat keys and ISO timestamp.
    """
    global _first_publish_logged
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    # Send HA discovery on first reading for this sensor
    publish_ha_discovery_for_sensor(sensor_name)

    topic = _topic(f"sensor/{sensor_name}/state")
    payload = json.dumps({
        "sensor": sensor_name,
        "hostname": _hostname,
        "temperature_c": round(temperature, 1),
        "timestamp": _now_iso(),
    })

    result = client.publish(topic, payload, qos=1, retain=True)
    success = result.rc == 0

    # Log the first successful publish to confirm data is flowing
    if success and not _first_publish_logged:
        logger.info("MQTT publishing active - first reading sent for %s", sensor_name)
        _first_publish_logged = True
    elif not success:
        logger.warning("MQTT publish failed for %s (rc=%d)", sensor_name, result.rc)

    return success


def publish_system_metrics(metrics: dict) -> bool:
    """Publish comprehensive system metrics to MQTT.

    Payload includes hostname for multi-Pi aggregation in Grafana/Node-RED.
    """
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    # Send HA discovery on first publish
    publish_ha_discovery_for_system()

    topic = _topic("system/state")
    metrics["hostname"] = _hostname
    metrics["timestamp"] = _now_iso()

    result = client.publish(topic, json.dumps(metrics), qos=1, retain=True)
    return result.rc == 0


def publish_alert(sensor_name: str, level: str, temperature: float) -> bool:
    """Publish an alert event to MQTT.

    Designed for HA automations - use the 'level' field to trigger
    different actions (e.g. flash lights red for EMERGENCY).
    """
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    topic = _topic("alerts")
    payload = json.dumps({
        "event": "alert",
        "sensor": sensor_name,
        "hostname": _hostname,
        "level": level,
        "temperature_c": round(temperature, 1),
        "timestamp": _now_iso(),
    })

    result = client.publish(topic, payload, qos=1)
    return result.rc == 0


def publish_recovery(sensor_name: str, temperature: float, previous_level: str) -> bool:
    """Publish a recovery event to MQTT."""
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    topic = _topic("recovery")
    payload = json.dumps({
        "event": "recovery",
        "sensor": sensor_name,
        "hostname": _hostname,
        "temperature_c": round(temperature, 1),
        "previous_level": previous_level,
        "timestamp": _now_iso(),
    })

    result = client.publish(topic, payload, qos=1)
    return result.rc == 0


def publish_online() -> bool:
    """Publish an online status message (for HA availability tracking)."""
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    topic = _topic("status")
    result = client.publish(topic, "online", qos=1, retain=True)
    return result.rc == 0


def publish_ha_discovery_for_fr24() -> None:
    """Register fr24feed metrics with Home Assistant auto-discovery."""
    state_topic = _topic("service/fr24feed/state")

    sensors = [
        ("fr24_aircraft_tracked", "FR24 Aircraft Tracked", "", "{{ value_json.aircraft_tracked }}", None, "mdi:airplane"),
        ("fr24_aircraft_uploaded", "FR24 Aircraft Uploaded", "", "{{ value_json.aircraft_uploaded }}", None, "mdi:upload"),
    ]

    for sensor_id, name, unit, template, device_class, icon in sensors:
        _send_ha_discovery(
            sensor_id=sensor_id,
            name=name,
            unit=unit,
            state_topic=state_topic,
            value_template=template,
            device_class=device_class,
            icon=icon,
        )

    # Binary sensor for feed connection status
    _send_ha_discovery(
        sensor_id="fr24_feed_connected",
        name="FR24 Feed Connected",
        unit="",
        state_topic=state_topic,
        value_template="{{ value_json.feed_connected }}",
        device_class="connectivity",
        icon="mdi:access-point-network",
        component="binary_sensor",
    )


def publish_ha_discovery_for_readsb() -> None:
    """Register readsb metrics with Home Assistant auto-discovery."""
    state_topic = _topic("service/readsb/state")

    sensors = [
        ("readsb_aircraft_total", "ADS-B Aircraft Total", "", "{{ value_json.aircraft_total }}", None, "mdi:airplane"),
        ("readsb_aircraft_with_pos", "ADS-B Aircraft With Position", "", "{{ value_json.aircraft_with_position }}", None, "mdi:map-marker"),
        ("readsb_aircraft_mlat", "ADS-B Aircraft MLAT", "", "{{ value_json.aircraft_with_mlat }}", None, "mdi:satellite-variant"),
        ("readsb_messages_rate", "ADS-B Message Rate", "msg/s", "{{ value_json.messages_rate }}", None, "mdi:message-fast"),
        ("readsb_messages_total", "ADS-B Messages Total", "", "{{ value_json.messages_total }}", None, "mdi:counter"),
        ("readsb_signal_mean", "ADS-B Signal Mean", "dBFS", "{{ value_json.signal_mean_dbfs }}", "signal_strength", "mdi:signal"),
        ("readsb_signal_peak", "ADS-B Signal Peak", "dBFS", "{{ value_json.signal_peak_dbfs }}", "signal_strength", "mdi:signal"),
        ("readsb_noise", "ADS-B Noise Floor", "dBFS", "{{ value_json.noise_dbfs }}", None, "mdi:waveform"),
        ("readsb_tracks", "ADS-B Tracks", "", "{{ value_json.tracks_all }}", None, "mdi:radar"),
        ("readsb_local_clients", "ADS-B Local Clients", "", "{{ value_json.local_clients }}", None, "mdi:lan-connect"),
    ]

    for sensor_id, name, unit, template, device_class, icon in sensors:
        _send_ha_discovery(
            sensor_id=sensor_id,
            name=name,
            unit=unit,
            state_topic=state_topic,
            value_template=template,
            device_class=device_class,
            icon=icon,
        )


def publish_ha_discovery_for_collector(service_name: str, stats: dict) -> None:
    """Auto-generate HA discovery for any collector based on its payload keys.

    Iterates the stats dict and registers a sensor entity for each
    numeric or boolean field. Skips 'timestamp' and string fields.
    """
    state_topic = _topic(f"service/{service_name}/state")

    # Map of known field patterns to HA metadata
    _FIELD_META = {
        "battery_charge": ("%", "battery", "mdi:battery"),
        "battery_runtime_sec": ("s", "duration", "mdi:timer"),
        "input_voltage": ("V", "voltage", "mdi:flash"),
        "output_voltage": ("V", "voltage", "mdi:flash"),
        "load_percent": ("%", "power_factor", "mdi:gauge"),
        "temperature_c": ("°C", "temperature", None),
        "power_on_hours": ("h", "duration", "mdi:clock-outline"),
        "offset_ms": ("ms", None, "mdi:clock-alert"),
        "root_delay_ms": ("ms", None, "mdi:timer-sand"),
        "stratum": ("", None, "mdi:layers"),
        "satellites_visible": ("", None, "mdi:satellite-variant"),
        "satellites_used": ("", None, "mdi:satellite-uplink"),
        "hdop": ("", None, "mdi:crosshairs-gps"),
        "altitude_m": ("m", None, "mdi:altimeter"),
        "fix_type": ("", None, "mdi:crosshairs-gps"),
        "dns_queries_today": ("", None, "mdi:dns"),
        "ads_blocked_today": ("", None, "mdi:shield-check"),
        "ads_percentage_today": ("%", None, "mdi:shield-half-full"),
        "block_percentage": ("%", None, "mdi:shield-half-full"),
        "blocked_today": ("", None, "mdi:shield-check"),
        "active_connections": ("", None, "mdi:server-network"),
        "requests": ("", None, "mdi:web"),
        "peers_total": ("", None, "mdi:account-group"),
        "peers_online": ("", None, "mdi:account-check"),
        "peers_active": ("", None, "mdi:account-check"),
        "containers_running": ("", None, "mdi:docker"),
        "containers_total": ("", None, "mdi:docker"),
        "images": ("", None, "mdi:layers"),
        "active_sessions": ("", None, "mdi:play-circle"),
        "devices_total": ("", None, "mdi:zigbee"),
        "cache_hit_ratio": ("%", None, "mdi:cached"),
        "total_queries": ("", None, "mdi:dns"),
        "services_running": ("", None, "mdi:check-circle"),
        "services_failed": ("", None, "mdi:alert-circle"),
        "aircraft_total": ("", None, "mdi:airplane"),
        "aircraft_with_position": ("", None, "mdi:map-marker"),
        "messages_rate": ("msg/s", None, "mdi:message-fast"),
        "signal_mean_dbfs": ("dBFS", "signal_strength", "mdi:signal"),
    }

    for key, value in stats.items():
        # Skip non-metric fields
        if key in ("timestamp", "hostname", "status", "source", "reference",
                   "tailnet_name", "server_name", "version", "device",
                   "feed_connection_type", "build_version", "feed_alias",
                   "message", "services", "coordinator_type"):
            continue

        # Only register numeric and boolean values
        if not isinstance(value, (int, float, bool)):
            continue

        sensor_id = f"svc_{service_name}_{key}"
        nice_name = key.replace("_", " ").title()

        unit, device_class, icon = _FIELD_META.get(key, ("", None, None))

        if isinstance(value, bool):
            _send_ha_discovery(
                sensor_id=sensor_id,
                name=f"{service_name.title()} {nice_name}",
                unit="",
                state_topic=state_topic,
                value_template="{{ value_json." + key + " }}",
                device_class="problem" if "fail" in key or "throttl" in key else None,
                icon=icon or "mdi:toggle-switch",
                component="binary_sensor",
            )
        else:
            _send_ha_discovery(
                sensor_id=sensor_id,
                name=f"{service_name.title()} {nice_name}",
                unit=unit,
                state_topic=state_topic,
                value_template="{{ value_json." + key + " }}",
                device_class=device_class,
                icon=icon or "mdi:information-outline",
            )


def publish_birth_message() -> bool:
    """Publish a birth message with system metadata on startup.

    Includes OS version, Python version, PiMon version, IP address,
    and system uptime for device identification in Home Assistant.
    """
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    import sys as _sys

    # Gather system information
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.read().split()[0])
    except (OSError, ValueError):
        uptime_seconds = 0.0

    try:
        import subprocess as _sp
        ip_result = _sp.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=5
        )
        ip_addr = ip_result.stdout.strip().split()[0] if ip_result.returncode == 0 else "unknown"
    except (OSError, IndexError):
        ip_addr = "unknown"

    from src import __version__

    payload = json.dumps({
        "hostname": _hostname,
        "pimon_version": __version__,
        "python_version": _sys.version.split()[0],
        "os_version": platform.platform(),
        "architecture": platform.machine(),
        "ip_address": ip_addr,
        "uptime_seconds": round(uptime_seconds, 1),
        "timestamp": _now_iso(),
    })

    topic = _topic("birth")
    result = client.publish(topic, payload, qos=1, retain=True)
    if result.rc == 0:
        logger.info("MQTT birth message published")
    return result.rc == 0
