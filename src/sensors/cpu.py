"""CPU temperature sensor for Raspberry Pi.

Reads from /sys/class/thermal/thermal_zone0/temp (zero-cost kernel read).
Falls back to the GPU module's cached vcgencmd result if thermal_zone
is unavailable.
"""

from pathlib import Path

from src.sensors.base import BaseSensor, SensorReading

_THERMAL_ZONE = Path("/sys/class/thermal/thermal_zone0/temp")


class CpuSensor(BaseSensor):
    """Reads the SoC CPU temperature from the kernel thermal zone."""

    @property
    def name(self) -> str:
        return "cpu"

    def is_available(self) -> bool:
        return _THERMAL_ZONE.exists()

    def read(self) -> SensorReading:
        try:
            if _THERMAL_ZONE.exists():
                # Direct kernel read - no subprocess needed
                raw = _THERMAL_ZONE.read_text().strip()
                temp = int(raw) / 1000.0
            else:
                # Fall back to shared vcgencmd cache from GPU module
                from src.sensors.gpu import _read_vcgencmd
                temp = _read_vcgencmd()
                if temp is None:
                    return SensorReading(
                        sensor_name=self.name,
                        temperature_c=0.0,
                        available=False,
                        error="No thermal source available",
                    )
            return SensorReading(sensor_name=self.name, temperature_c=temp)
        except (OSError, ValueError, IndexError) as exc:
            return SensorReading(
                sensor_name=self.name,
                temperature_c=0.0,
                available=False,
                error=str(exc),
            )
