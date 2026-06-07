"""System metrics collection for Raspberry Pi.

Gathers CPU usage, memory usage, disk usage, and throttling state
to provide context alongside temperature data.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SystemMetrics:
    """Snapshot of system resource usage."""

    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    throttled: bool
    throttle_flags: str


def collect_metrics() -> SystemMetrics:
    """Collect current system metrics from /proc and vcgencmd."""
    return SystemMetrics(
        cpu_percent=_cpu_percent(),
        memory_percent=_memory_percent()[0],
        memory_used_mb=_memory_percent()[1],
        memory_total_mb=_memory_percent()[2],
        disk_percent=_disk_percent()[0],
        disk_used_gb=_disk_percent()[1],
        disk_total_gb=_disk_percent()[2],
        throttled=_is_throttled(),
        throttle_flags=_throttle_flags(),
    )


def _cpu_percent() -> float:
    """Read CPU usage from /proc/stat (single sample - idle ratio)."""
    try:
        stat = Path("/proc/stat").read_text()
        line = stat.split("\n")[0]  # cpu aggregate line
        parts = line.split()[1:]  # skip 'cpu' label
        values = [int(v) for v in parts]
        idle = values[3]
        total = sum(values)
        if total == 0:
            return 0.0
        return round((1.0 - idle / total) * 100, 1)
    except (OSError, ValueError, IndexError):
        return 0.0


_mem_cache: tuple[float, float, float] | None = None


def _memory_percent() -> tuple[float, float, float]:
    """Read memory usage from /proc/meminfo."""
    global _mem_cache
    if _mem_cache is not None:
        return _mem_cache

    try:
        info = Path("/proc/meminfo").read_text()
        mem = {}
        for line in info.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                mem[key.strip()] = int(val.strip().split()[0])

        total_kb = mem.get("MemTotal", 0)
        available_kb = mem.get("MemAvailable", 0)
        used_kb = total_kb - available_kb
        total_mb = total_kb / 1024
        used_mb = used_kb / 1024
        percent = (used_kb / total_kb * 100) if total_kb > 0 else 0.0
        _mem_cache = (round(percent, 1), round(used_mb, 1), round(total_mb, 1))
        return _mem_cache
    except (OSError, ValueError, KeyError):
        return (0.0, 0.0, 0.0)


_disk_cache: tuple[float, float, float] | None = None


def _disk_percent() -> tuple[float, float, float]:
    """Read root filesystem disk usage."""
    global _disk_cache
    if _disk_cache is not None:
        return _disk_cache

    try:
        import shutil
        usage = shutil.disk_usage("/")
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        percent = (usage.used / usage.total * 100) if usage.total > 0 else 0.0
        _disk_cache = (round(percent, 1), round(used_gb, 1), round(total_gb, 1))
        return _disk_cache
    except OSError:
        return (0.0, 0.0, 0.0)


def _throttle_flags() -> str:
    """Read throttle state from vcgencmd."""
    try:
        result = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Output: throttled=0x0
        return result.stdout.strip().split("=")[1]
    except (OSError, IndexError, subprocess.SubprocessError):
        return "unknown"


def _is_throttled() -> bool:
    """Check if the Pi is currently throttled."""
    flags = _throttle_flags()
    if flags == "unknown":
        return False
    try:
        return int(flags, 16) != 0
    except ValueError:
        return False
