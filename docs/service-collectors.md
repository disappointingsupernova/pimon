# External Service Collectors

PiMon can auto-detect and publish statistics from co-hosted services via MQTT. This is useful for ADS-B feeder Pis running FlightRadar24 and readsb, DNS servers, media centres, and more.

## Auto-Detection Behaviour

Collectors use a tri-state configuration:

| .env Setting | Behaviour |
|---|---|
| Not set (default) | Auto-detect: if the service is running and responds, publish its stats |
| `true` | Force enabled: always attempt collection (errors logged if service not found) |
| `false` | Explicitly disabled: never attempt collection even if service is present |

On your ADS-B Pi, you do not need to configure anything. If fr24feed and readsb are running, their stats will be automatically detected and published.

## Configuration

| Field | Type | Default | Description |
|---|---|---|---|
| COLLECTOR_FR24_ENABLED | bool/unset | (auto) | FlightRadar24 feed stats collection |
| COLLECTOR_READSB_ENABLED | bool/unset | (auto) | readsb ADS-B decoder stats collection |
| COLLECTOR_READSB_STATS_DIR | string | /run/readsb | Path to readsb JSON stats directory |

## All Available Collectors

Every collector auto-detects its service. No configuration is needed unless noted.

| Service | MQTT Topic | Detection Method | Notes |
|---------|-----------|-----------------|-------|
| fr24feed | `service/fr24feed/state` | HTTP `127.0.0.1:8754` | - |
| readsb | `service/readsb/state` | JSON at `/run/readsb/` | Configurable path via `COLLECTOR_READSB_STATS_DIR` |
| dump1090-fa | `service/dump1090/state` | HTTP `127.0.0.1:8080/data/stats.json` | - |
| Pi-hole | `service/pihole/state` | HTTP `127.0.0.1/admin/api.php` | - |
| AdGuard Home | `service/adguard/state` | HTTP `127.0.0.1:3000/control/stats` | - |
| Unbound | `service/unbound/state` | `unbound-control stats_noreset` | - |
| WireGuard | `service/wireguard/state` | `wg show all dump` | Requires root or `cap_net_admin` |
| Tailscale | `service/tailscale/state` | `tailscale status --json` | - |
| Nginx | `service/nginx/state` | HTTP stub_status | Requires `stub_status` enabled in Nginx config |
| Plex | `service/plex/state` | HTTP `127.0.0.1:32400` | Set `PLEX_TOKEN` in .env for session data |
| Jellyfin | `service/jellyfin/state` | HTTP `127.0.0.1:8096` | Set `JELLYFIN_API_KEY` in .env for session data |
| Zigbee2MQTT | `service/zigbee2mqtt/state` | HTTP `127.0.0.1:8080/api/` | - |
| InfluxDB | `service/influxdb/state` | HTTP `127.0.0.1:8086/health` | - |
| Docker | `service/docker/state` | Unix socket `/var/run/docker.sock` | Service user needs docker group membership |
| UPS (NUT) | `service/ups/state` | `upsc` CLI | Set `UPS_NAME` in .env if not "ups" |
| SMART | `service/smart/state` | `smartctl -a --json` | Tries /dev/sda, /dev/nvme0, /dev/mmcblk0 |
| systemd | `service/systemd/state` | `systemctl is-active` | Set `SYSTEMD_MONITOR_SERVICES` in .env (comma-separated) |
| NTP/chrony | `service/ntp/state` | `chronyc tracking` or `ntpq -pn` | Reports stratum, offset, sync status |
| GPS (gpsd) | `service/gps/state` | TCP `127.0.0.1:2947` | Reports fix type, lat/lon, satellites, HDOP |

## Disabling Auto-Detection

To prevent a collector from running even when the service is present:

```bash
COLLECTOR_FR24_ENABLED=false
COLLECTOR_READSB_ENABLED=false
```

## FlightRadar24 (fr24feed)

Collects from fr24feed's local HTTP monitor endpoint (`http://127.0.0.1:8754/monitor.json`), falling back to the `fr24feed-status` CLI command.

MQTT topic: `pimon/<hostname>/service/fr24feed/state`

Payload:
```json
{
  "feed_connected": true,
  "aircraft_tracked": 17,
  "aircraft_uploaded": 15,
  "receiver_connected": true,
  "mlat_enabled": true,
  "feed_connection_type": "MLAT+BEAST",
  "build_version": "1.0.48",
  "timestamp": "2026-06-08T21:30:00+00:00"
}
```

Home Assistant entities auto-discovered:
- FR24 Aircraft Tracked (sensor)
- FR24 Aircraft Uploaded (sensor)
- FR24 Feed Connected (binary sensor with connectivity device class)

## readsb ADS-B Decoder

Reads JSON statistics from readsb's run directory (`/run/readsb/stats.json` and `/run/readsb/aircraft.json`).

MQTT topic: `pimon/<hostname>/service/readsb/state`

Payload:
```json
{
  "aircraft_total": 42,
  "aircraft_with_position": 38,
  "aircraft_with_mlat": 12,
  "messages_rate": 234.5,
  "messages_total": 1847293,
  "signal_mean_dbfs": -3.2,
  "signal_peak_dbfs": -0.8,
  "noise_dbfs": -28.4,
  "tracks_all": 156,
  "local_clients": 3,
  "remote_clients": 1,
  "cpu_demod_ms": 12.3,
  "cpu_reader_ms": 4.1,
  "cpu_background_ms": 2.0,
  "timestamp": "2026-06-08T21:30:00+00:00"
}
```

Home Assistant entities auto-discovered:
- ADS-B Aircraft Total (sensor)
- ADS-B Aircraft With Position (sensor)
- ADS-B Aircraft MLAT (sensor)
- ADS-B Message Rate (sensor, msg/s)
- ADS-B Messages Total (sensor)
- ADS-B Signal Mean (sensor, dBFS)
- ADS-B Signal Peak (sensor, dBFS)
- ADS-B Noise Floor (sensor, dBFS)
- ADS-B Tracks (sensor)
- ADS-B Local Clients (sensor)

## NTP / Chrony

Auto-detects chrony (preferred) or ntpd and publishes time synchronisation health.

MQTT topic: `pimon/<hostname>/service/ntp/state`

Payload:
```json
{
  "source": "chrony",
  "reference": "GPS (PPS)",
  "stratum": 1,
  "offset_ms": 0.023,
  "root_delay_ms": 0.001,
  "synchronised": true,
  "timestamp": "2026-06-08T21:30:00+00:00"
}
```

## GPS (gpsd)

Auto-detects gpsd by connecting to its default TCP port (2947). Useful for ADS-B feeders that use GPS for MLAT synchronisation.

MQTT topic: `pimon/<hostname>/service/gps/state`

Payload:
```json
{
  "fix_type": 3,
  "latitude": 51.5074,
  "longitude": -0.1278,
  "altitude_m": 45.2,
  "speed_kmh": 0.0,
  "satellites_visible": 12,
  "satellites_used": 9,
  "hdop": 0.8,
  "timestamp": "2026-06-08T21:30:00+00:00"
}
```
