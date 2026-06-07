"""GPU temperature sensor for Raspberry Pi.

Uses vcgencmd to read the VideoCore GPU temperature.
"""

import subprocess

from src.sensors.base import BaseSensor, SensorReading


class GpuSensor(BaseSensor):
    """Reads the VideoCore GPU temperature via vcgencmd."""

    @property
    def name(self) -> str:
        return "gpu"

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def read(self) -> SensorReading:
        try:
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
