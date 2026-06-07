"""CPU temperature sensor for Raspberry Pi.

Reads from /sys/class/thermal/thermal_zone0/temp with vcgencmd as fallback.
"""

import subprocess
from pathlib import Path

from src.sensors.base import BaseSensor, SensorReading

_THERMAL_ZONE = Path("/sys/class/thermal/thermal_zone0/temp")


class CpuSensor(BaseSensor):
    """Reads the SoC CPU temperature."""

    @property
    def name(self) -> str:
        return "cpu"

    def is_available(self) -> bool:
        return _THERMAL_ZONE.exists()

    def read(self) -> SensorReading:
        try:
            if _THERMAL_ZONE.exists():
                raw = _THERMAL_ZONE.read_text().strip()
                temp = int(raw) / 1000.0
            else:
                result = subprocess.run(
                    ["vcgencmd", "measure_temp"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # Output format: temp=42.8'C
                temp = float(result.stdout.split("=")[1].split("'")[0])
            return SensorReading(sensor_name=self.name, temperature_c=temp)
        except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
            return SensorReading(
                sensor_name=self.name,
                temperature_c=0.0,
                available=False,
                error=str(exc),
            )
