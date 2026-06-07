"""MQTT publisher for Pi Temperature Alerter.

Publishes temperature readings and alerts to an MQTT broker for
integration with Home Assistant or other IoT platforms.
"""

import json
import logging

from src.config import config

logger = logging.getLogger("pi_temp_alerter")

_client = None


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


def publish_reading(sensor_name: str, temperature: float) -> bool:
    """Publish a sensor reading to MQTT."""
    if not config.mqtt_enabled:
        return False

    client = _get_client()
    if client is None:
        return False

    topic = f"{config.mqtt_topic_prefix}/{sensor_name}/temperature"
    payload = json.dumps({
        "sensor": sensor_name,
        "temperature_c": temperature,
    })

    result = client.publish(topic, payload, qos=1, retain=True)
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
        "sensor": sensor_name,
        "level": level,
        "temperature_c": temperature,
    })

    result = client.publish(topic, payload, qos=1)
    return result.rc == 0
