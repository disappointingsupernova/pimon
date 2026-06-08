"""Centralised service collector registry for PiMon.

Provides a single entry point to run all collectors, cache their
results, and expose them to Prometheus, MQTT, alerting, and the
dashboard API. Each collector is run safely with error isolation.
"""

import importlib
import logging
import time
from typing import Any

from src.config import config

logger = logging.getLogger("pimon")

# Registry: (config_attr_or_none, module_path, function_name, service_name)
COLLECTORS: list[tuple[str | None, str, str, str]] = [
    ("collector_fr24_enabled", "src.sensors.collectors.fr24feed", "collect_fr24_stats", "fr24feed"),
    ("collector_readsb_enabled", "src.sensors.collectors.readsb", "collect_readsb_stats", "readsb"),
    (None, "src.sensors.collectors.pihole", "collect_pihole_stats", "pihole"),
    (None, "src.sensors.collectors.adguard", "collect_adguard_stats", "adguard"),
    (None, "src.sensors.collectors.unbound", "collect_unbound_stats", "unbound"),
    (None, "src.sensors.collectors.wireguard", "collect_wireguard_stats", "wireguard"),
    (None, "src.sensors.collectors.tailscale", "collect_tailscale_stats", "tailscale"),
    (None, "src.sensors.collectors.nginx", "collect_nginx_stats", "nginx"),
    (None, "src.sensors.collectors.plex", "collect_plex_stats", "plex"),
    (None, "src.sensors.collectors.jellyfin", "collect_jellyfin_stats", "jellyfin"),
    (None, "src.sensors.collectors.zigbee2mqtt", "collect_zigbee2mqtt_stats", "zigbee2mqtt"),
    (None, "src.sensors.collectors.influxdb", "collect_influxdb_stats", "influxdb"),
    (None, "src.sensors.collectors.docker", "collect_docker_stats", "docker"),
    (None, "src.sensors.collectors.dump1090", "collect_dump1090_stats", "dump1090"),
    (None, "src.sensors.collectors.ups", "collect_ups_stats", "ups"),
    (None, "src.sensors.collectors.smart", "collect_smart_stats", "smart"),
    (None, "src.sensors.collectors.systemd", "collect_systemd_stats", "systemd"),
    (None, "src.sensors.collectors.ntp", "collect_ntp_stats", "ntp"),
    (None, "src.sensors.collectors.gps", "collect_gps_stats", "gps"),
]

# Cached results from the last collection run
_last_results: dict[str, dict[str, Any]] = {}
_last_run_time: float = 0.0


def collect_all() -> dict[str, dict[str, Any]]:
    """Run all enabled collectors and return {service_name: stats_dict}.

    Skips explicitly disabled collectors and those that return None.
    Each collector is wrapped in a try/except so a single failure
    cannot affect others.
    """
    global _last_results, _last_run_time
    results: dict[str, dict[str, Any]] = {}

    for config_attr, module_path, func_name, service_name in COLLECTORS:
        # Check if explicitly disabled
        if config_attr:
            state = getattr(config, config_attr, None)
            if state is False:
                continue

        try:
            mod = importlib.import_module(module_path)
            collect_fn = getattr(mod, func_name)
            stats = collect_fn()
            if stats:
                results[service_name] = stats
        except Exception:
            pass

    _last_results = results
    _last_run_time = time.monotonic()
    return results


def get_cached_results() -> dict[str, dict[str, Any]]:
    """Return the most recently cached collector results."""
    return _last_results


def get_numeric_metrics(stats: dict[str, Any]) -> dict[str, float | int | bool]:
    """Extract only numeric and boolean fields from a collector stats dict.

    Filters out string/metadata fields that are not suitable for metrics.
    """
    _SKIP_KEYS = frozenset({
        "timestamp", "hostname", "status", "source", "reference",
        "tailnet_name", "server_name", "version", "device",
        "feed_connection_type", "build_version", "feed_alias",
        "message", "services", "coordinator_type",
    })
    return {
        k: v for k, v in stats.items()
        if k not in _SKIP_KEYS and isinstance(v, (int, float, bool))
    }
