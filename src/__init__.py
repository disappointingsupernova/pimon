"""PiMon - Raspberry Pi system health monitoring."""

import subprocess
from pathlib import Path

_FALLBACK_VERSION = "1.0.0"


def _get_version() -> str:
    """Derive version from git commit hash if available, otherwise fall back.

    Returns the short commit hash prefixed with the base version
    (e.g. '1.0.0+abc1234'). If git is unavailable or not a repo,
    returns the fallback version string without crashing.
    """
    try:
        repo_dir = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            commit_hash = result.stdout.strip()
            return f"{_FALLBACK_VERSION}+{commit_hash}"
    except (OSError, subprocess.SubprocessError):
        pass
    return _FALLBACK_VERSION


__version__ = _get_version()
