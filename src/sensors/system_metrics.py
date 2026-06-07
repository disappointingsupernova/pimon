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
    mem = _memory_usage()
    disk = _disk_usage()

    # Read throttle flags once and derive the boolean from it
    flags = _throttle_flags()
    throttled = _parse_throttled(flags)

    return SystemMetrics(
        cpu_percent=_cpu_percent(),
        memory_percent=mem[0],
        memory_used_mb=mem[1],
        memory_total_mb=mem[2],
        disk_percent=disk[0],
        disk_used_gb=disk[1],
        disk_total_gb=disk[2],
        throttled=throttled,
        throttle_flags=flags,
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


def _memory_usage() -> tuple[float, float, float]:
    """Read memory usage from /proc/meminfo. Always reads fresh data."""
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
        return (round(percent, 1), round(used_mb, 1), round(total_mb, 1))
    except (OSError, ValueError, KeyError):
        return (0.0, 0.0, 0.0)


def _disk_usage() -> tuple[float, float, float]:
    """Read root filesystem disk usage. Always reads fresh data."""
    try:
        import shutil
        usage = shutil.disk_usage("/")
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        percent = (usage.used / usage.total * 100) if usage.total > 0 else 0.0
        return (round(percent, 1), round(used_gb, 1), round(total_gb, 1))
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


def _parse_throttled(flags: str) -> bool:
    """Parse the throttle flags string into a boolean."""
    if flags == "unknown":
        return False
    try:
        return int(flags, 16) != 0
    except ValueError:
        return False


def _is_throttled() -> bool:
    """Check if the Pi is currently throttled."""
    return _parse_throttled(_throttle_flags())
