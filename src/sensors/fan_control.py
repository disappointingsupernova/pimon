"""GPIO fan control for Raspberry Pi.

Controls a fan connected to a GPIO pin based on temperature thresholds.
Uses separate thresholds from alerting to allow independent control.
"""

import logging

from src.config import config

logger = logging.getLogger("pimon")

_fan_state: bool = False
_gpio_initialised: bool = False


def _init_gpio() -> bool:
    """Initialise the GPIO pin for fan control."""
    global _gpio_initialised
    if _gpio_initialised:
        return True

    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.fan_gpio_pin, GPIO.OUT)
        GPIO.output(config.fan_gpio_pin, GPIO.LOW)
        _gpio_initialised = True
        logger.info("Fan control initialised on GPIO %d", config.fan_gpio_pin)
        return True
    except (ImportError, RuntimeError) as exc:
        logger.warning("GPIO unavailable for fan control: %s", exc)
        return False


def update_fan(temperature: float) -> None:
    """Update fan state based on the given temperature.

    Turns on at fan_on_threshold, turns off at fan_off_threshold.
    Hysteresis is built in via the two separate thresholds.
    """
    global _fan_state

    if not config.fan_control_enabled:
        return

    if not _init_gpio():
        return

    if not _fan_state and temperature >= config.fan_on_threshold:
        _set_fan(True)
    elif _fan_state and temperature <= config.fan_off_threshold:
        _set_fan(False)


def _set_fan(state: bool) -> None:
    """Set the fan GPIO pin high or low."""
    global _fan_state
    try:
        import RPi.GPIO as GPIO
        GPIO.output(config.fan_gpio_pin, GPIO.HIGH if state else GPIO.LOW)
        _fan_state = state
        logger.info("Fan %s (GPIO %d)", "ON" if state else "OFF", config.fan_gpio_pin)
    except (ImportError, RuntimeError) as exc:
        logger.error("Failed to set fan state: %s", exc)


def cleanup() -> None:
    """Clean up GPIO on shutdown."""
    global _gpio_initialised
    if not _gpio_initialised:
        return
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup(config.fan_gpio_pin)
        _gpio_initialised = False
    except (ImportError, RuntimeError):
        pass
