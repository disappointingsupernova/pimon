"""DS18B20 one-wire temperature sensor support.

Discovers and reads all connected DS18B20 sensors from the one-wire bus.
Requires the w1-gpio and w1-therm kernel modules to be loaded.
"""

from pathlib import Path

from src.config import config
from src.sensors.base import BaseSensor, SensorReading

_DEVICE_PREFIX = "28-"


class Ds18b20Sensor(BaseSensor):
    """Reads temperature from a single DS18B20 sensor."""

    def __init__(self, device_id: str) -> None:
        self._device_id = device_id
        self._device_path = Path(config.ds18b20_base_dir) / device_id / "w1_slave"

    @property
    def name(self) -> str:
        return f"ds18b20_{self._device_id}"

    def is_available(self) -> bool:
        return self._device_path.exists()

    def read(self) -> SensorReading:
        try:
            content = self._device_path.read_text()
            lines = content.strip().split("\n")

            # First line ends with YES if CRC is valid
            if not lines[0].strip().endswith("YES"):
                return SensorReading(
                    sensor_name=self.name,
                    temperature_c=0.0,
                    available=False,
                    error="CRC check failed",
                )

            # Second line contains t=<millidegrees>
            temp_str = lines[1].split("t=")[1]
            temp = int(temp_str) / 1000.0
            return SensorReading(sensor_name=self.name, temperature_c=temp)
        except (OSError, ValueError, IndexError) as exc:
            return SensorReading(
                sensor_name=self.name,
                temperature_c=0.0,
                available=False,
                error=str(exc),
            )


def discover_ds18b20_sensors() -> list[Ds18b20Sensor]:
    """Scan the one-wire bus and return sensor instances for each DS18B20 found."""
    base = Path(config.ds18b20_base_dir)
    if not base.exists():
        return []

    sensors = []
    for device_dir in sorted(base.iterdir()):
        if device_dir.name.startswith(_DEVICE_PREFIX):
            sensors.append(Ds18b20Sensor(device_dir.name))
    return sensors
