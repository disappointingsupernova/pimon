"""GPU temperature sensor for Raspberry Pi.

Uses vcgencmd to read the VideoCore GPU temperature. Caches the result
for a short TTL to avoid redundant subprocess spawns when both CPU and
GPU sensors are read in the same poll cycle.
"""

import subprocess
import time

from src.sensors.base import BaseSensor, SensorReading

# Cache vcgencmd result for 2 seconds to avoid redundant subprocess spawns
# when multiple reads occur within the same poll cycle
_cache_value: float | None = None
_cache_time: float = 0.0
_CACHE_TTL = 2.0


def _read_vcgencmd() -> float | None:
    """Read temperature from vcgencmd with short-lived caching."""
    global _cache_value, _cache_time

    now = time.monotonic()
    if _cache_value is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache_value

    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        # Output format: temp=42.8'C
        temp = float(result.stdout.split("=")[1].split("'")[0])
        _cache_value = temp
        _cache_time = now
        return temp
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


class GpuSensor(BaseSensor):
    """Reads the VideoCore GPU temperature via vcgencmd."""

    @property
    def name(self) -> str:
        return "gpu"

    def is_available(self) -> bool:
        return _read_vcgencmd() is not None

    def read(self) -> SensorReading:
        temp = _read_vcgencmd()
        if temp is not None:
            return SensorReading(sensor_name=self.name, temperature_c=temp)
        return SensorReading(
            sensor_name=self.name,
            temperature_c=0.0,
            available=False,
            error="vcgencmd unavailable",
        )
