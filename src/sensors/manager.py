"""Sensor manager that orchestrates all enabled temperature sensors."""

import logging

from src.config import config
from src.sensors.base import BaseSensor, SensorReading
from src.sensors.cpu import CpuSensor
from src.sensors.ds18b20 import discover_ds18b20_sensors
from src.sensors.gpu import GpuSensor

logger = logging.getLogger("pimon")


class SensorManager:
    """Discovers, initialises, and reads from all configured sensors.

    Checks sensor availability at startup and only registers those
    that are accessible, avoiding repeated warnings in the poll loop.
    """

    def __init__(self) -> None:
        self._sensors: list[BaseSensor] = []
        self._initialise_sensors()

    def _initialise_sensors(self) -> None:
        if config.sensor_cpu_enabled:
            sensor = CpuSensor()
            if sensor.is_available():
                self._sensors.append(sensor)
            else:
                logger.warning("CPU sensor not available on this system, skipping")

        if config.sensor_gpu_enabled:
            sensor = GpuSensor()
            if sensor.is_available():
                self._sensors.append(sensor)
            else:
                logger.warning("GPU sensor (vcgencmd) not available on this system, skipping")

        if config.sensor_ds18b20_enabled:
            ds_sensors = discover_ds18b20_sensors()
            if ds_sensors:
                self._sensors.extend(ds_sensors)
            else:
                logger.warning("No DS18B20 sensors found")

    @property
    def sensors(self) -> list[BaseSensor]:
        return list(self._sensors)

    def read_all(self) -> list[SensorReading]:
        """Read temperature from all registered sensors."""
        return [sensor.read() for sensor in self._sensors]

    def get_sensor(self, name: str) -> BaseSensor | None:
        """Retrieve a sensor by name."""
        for sensor in self._sensors:
            if sensor.name == name:
                return sensor
        return None
