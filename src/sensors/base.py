"""Base sensor interface for Pi Temperature Alerter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SensorReading:
    """A single temperature reading from a sensor."""

    sensor_name: str
    temperature_c: float
    available: bool = True
    error: str | None = None


class BaseSensor(ABC):
    """Abstract base class for temperature sensors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable sensor name."""

    @abstractmethod
    def read(self) -> SensorReading:
        """Take a temperature reading. Returns a SensorReading."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the sensor hardware is accessible."""
