"""Alert template rendering for PiMon.

Loads Jinja2 templates from the templates/ directory for alert and
recovery notifications. Falls back to built-in defaults if template
files are missing.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from src.config import config

logger = logging.getLogger("pimon")

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

_LEVEL_COLOURS = {
    "WARNING": "#f39c12",
    "CRITICAL": "#e74c3c",
    "EMERGENCY": "#8e44ad",
}

_env: Environment | None = None


def _get_env() -> Environment:
    """Lazily initialise the Jinja2 environment."""
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=False,
        )
    return _env


def render_alert(
    level: str,
    sensor_name: str,
    temperature_c: float,
    template_name: str = "alert",
) -> tuple[str, str | None]:
    """Render alert notification text (and optional HTML).

    Returns (plain_text, html_or_none).
    """
    context = _build_context(level, sensor_name, temperature_c)
    plain = _render(f"{template_name}.txt.j2", context)
    html = _render(f"{template_name}.html.j2", context)
    return plain, html


def render_recovery(
    sensor_name: str,
    temperature_c: float,
    previous_level: str,
) -> tuple[str, str | None]:
    """Render recovery notification text (and optional HTML).

    Returns (plain_text, html_or_none).
    """
    context = _build_context(previous_level, sensor_name, temperature_c)
    context["previous_level"] = previous_level
    plain = _render("recovery.txt.j2", context)
    html = _render("recovery.html.j2", context)
    return plain, html


def _build_context(level: str, sensor_name: str, temperature_c: float) -> dict:
    """Build the template context dictionary."""
    return {
        "level": level,
        "sensor_name": sensor_name,
        "temperature_c": temperature_c,
        "thresholds": config.get_thresholds(sensor_name),
        "colour": _LEVEL_COLOURS.get(level, "#333"),
        "dashboard_url": f"http://{config.dashboard_host}:{config.dashboard_port}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def _render(template_name: str, context: dict) -> str | None:
    """Render a single template, returning None if not found."""
    try:
        env = _get_env()
        tmpl = env.get_template(template_name)
        return tmpl.render(**context)
    except TemplateNotFound:
        return None
    except Exception as exc:
        logger.warning("Failed to render template %s: %s", template_name, exc)
        return None
