"""Sensor manager that orchestrates all enabled temperature sensors."""

from src.config import config
from src.sensors.base import BaseSensor, SensorReading
from src.sensors.cpu import CpuSensor
from src.sensors.ds18b20 import discover_ds18b20_sensors
from src.sensors.gpu import GpuSensor


class SensorManager:
    """Discovers, initialises, and reads from all configured sensors."""

    def __init__(self) -> None:
        self._sensors: list[BaseSensor] = []
        self._initialise_sensors()

    def _initialise_sensors(self) -> None:
        if config.sensor_cpu_enabled:
            self._sensors.append(CpuSensor())

        if config.sensor_gpu_enabled:
            self._sensors.append(GpuSensor())

        if config.sensor_ds18b20_enabled:
            self._sensors.extend(discover_ds18b20_sensors())

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
