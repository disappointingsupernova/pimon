"""MQTT publisher for Pi Temperature Alerter.

Publishes temperature readings, system metrics, alerts, and recovery
events to an MQTT broker. Supports Home Assistant MQTT auto-discovery
so all sensors appear automatically without manual configuration.

Topic structure:
    <prefix>/sensor/<name>/state       - Temperature reading (retained)
    <prefix>/system/state              - System metrics (retained)
    <prefix>/alerts                    - Alert events (not retained)
    <prefix>/recovery                  - Recovery events (not retained)
    homeassistant/sensor/<id>/config   - HA discovery (retained)
"""

import json
import logging
import platform
import time
from datetime import datetime, timezone

from src.config import config

logger = logging.getLogger("pi_temp_alerter")

_client = None
_discovery_sent: set[str] = set()


def _get_client():
    """Lazily initialise the MQTT client."""
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

    try:
        _client.connect(config.mqtt_host, config.mqtt_port, keepalive=60)
        _client.loop_start()
        logger.info("MQTT connected to %s:%d", config.mqtt_host, config.mqtt_port)
    except (OSError, Exception) as exc:
        logger.error("MQTT connection failed: %s", exc)
        _client = None

    return _client


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _device_info() -> dict:
    """Return device metadata for Home Assistant discovery."""
    return {
        "identifiers": [config.mqtt_client_id],
        "name": "Pi Temperature Alerter",
        "manufacturer": "Raspberry Pi",
        "model": platform.machine(),
        "sw_version": "1.0.0",
    }


# =============================================================================
# Home Assistant MQTT Auto-Discovery
# =============================================================================

def _send_ha_discovery(sensor_id: str, name: str, unit: str,
                       state_topic: str, value_template: str,
                       device_class: str | None = None,
                       icon: str | None = None) -> None:
    """Publish a Home Assistant MQTT discovery config message.

    Only sent once per sensor per session to avoid spamming the broker.
    """
    if sensor_id in _discovery_sent:
        return

    client = _get_client()
    if client is None:
        return

    unique_id = f"{config.mqtt_client_id}_{sensor_id}"
    discovery_topic = f"homeassistant/sensor/{unique_id}/config"

    payload = {
        "name": name,
        "unique_id": unique_id,
        "state_topic": state_topic,
        "value_template": value_template,
        "unit_of_measurement": unit,
        "device": _device_info(),
        "availability_topic": f"{config.mqtt_topic_prefix}/status",
        "payload_available": "online",
        "payload_not_available": "offline",
    }

    if device_class:
        payload["device_class"] = device_class
    if icon:
        payload["icon"] = icon

    client.publish(discovery_topic, json.dumps(payload), qos=1, retain=True)
    _discovery_sent.add(sensor_id)


def publish_ha_discovery_for_sensor(sensor_name: str) -> None:
    """Register a temperature sensor with Home Assistant auto-discovery."""
    state_topic = f"{config.mqtt_topic_prefix}/sensor/{sensor_name}/state"
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
    state_topic = f"{config.mqtt_topic_prefix}/system/state"

    metrics = [
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
        ("throttled", "Throttled", "", "{{ value_json.throttled }}", None, "mdi:alert-circle"),
    ]

    for sensor_id, name, unit, template, device_class, icon in metrics:
        _send_ha_discovery(
            sensor_id=f"sys_{sensor_id}",
            name=name,
            unit=unit,
            state_topic=state_topic,
            value_template=template,
            device_class=device_class,
            icon=icon,
        )


# =============================================================================
# Publishing functions
# =============================================================================

def publish_reading(sensor_name: str, temperature: float) -> bool:
    """Publish a sensor temperature reading to MQTT."""
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    # Send HA discovery on first reading for this sensor
    publish_ha_discovery_for_sensor(sensor_name)

    topic = f"{config.mqtt_topic_prefix}/sensor/{sensor_name}/state"
    payload = json.dumps({
        "sensor": sensor_name,
        "temperature_c": round(temperature, 1),
        "timestamp": _now_iso(),
    })

    result = client.publish(topic, payload, qos=1, retain=True)
    return result.rc == 0


def publish_system_metrics(metrics: dict) -> bool:
    """Publish comprehensive system metrics to MQTT.

    Expects a dict with keys matching the system metrics collected
    by the extended collector.
    """
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    # Send HA discovery on first publish
    publish_ha_discovery_for_system()

    topic = f"{config.mqtt_topic_prefix}/system/state"
    metrics["timestamp"] = _now_iso()

    result = client.publish(topic, json.dumps(metrics), qos=1, retain=True)
    return result.rc == 0


def publish_alert(sensor_name: str, level: str, temperature: float) -> bool:
    """Publish an alert event to MQTT."""
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    topic = f"{config.mqtt_topic_prefix}/alerts"
    payload = json.dumps({
        "event": "alert",
        "sensor": sensor_name,
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

    topic = f"{config.mqtt_topic_prefix}/recovery"
    payload = json.dumps({
        "event": "recovery",
        "sensor": sensor_name,
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

    topic = f"{config.mqtt_topic_prefix}/status"
    result = client.publish(topic, "online", qos=1, retain=True)
    return result.rc == 0
