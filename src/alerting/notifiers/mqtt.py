"""MQTT publisher for Pi Temperature Alerter.

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

logger = logging.getLogger("pi_temp_alerter")

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
    return {
        "identifiers": [config.mqtt_client_id],
        "name": f"Pi Temp Alerter ({_hostname})",
        "manufacturer": "Raspberry Pi",
        "model": platform.machine(),
        "sw_version": "1.0.0",
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
