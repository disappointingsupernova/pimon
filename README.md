# Pi Temperature Alerter

A comprehensive Raspberry Pi temperature monitoring and alerting system. Monitors CPU, GPU, and external DS18B20 sensors with configurable email alerts, hysteresis-based threshold evaluation, and a real-time web dashboard.

## Features

- Multi-sensor support: CPU (thermal_zone), GPU (vcgencmd), DS18B20 (one-wire)
- Tiered alerting: Warning, Critical, and Emergency thresholds with per-level recipients
- Per-sensor threshold overrides for different acceptable ranges
- Hysteresis: Prevents alert flapping when temperature oscillates around a threshold
- Cooldown: Rate-limits repeated alerts to avoid inbox flooding
- Recovery notifications: Alerts when temperature returns to normal
- Rate-of-change alerting: Detects rapid temperature rises
- Alert escalation timeout: Auto-escalates if stuck at a level too long
- Multi-channel notifications: Email, Webhook, Telegram, Pushover, MQTT
- HTML emails with colour-coded severity and dashboard links
- Web dashboard: Real-time Chart.js graphs with auto-refresh and optional auth
- Per-endpoint toggle: Individually enable/disable API, health, and metrics routes
- Prometheus /metrics endpoint for Grafana integration
- System metrics: CPU, memory, disk usage, and throttle state
- Database persistence: SQLAlchemy with SQLite (default), MySQL, or PostgreSQL
- CSV logging with daily rotation and configurable retention
- Daily digest email with min/max/average statistics
- GPIO fan control with independent on/off thresholds
- Systemd integration: Auto-start on boot with security hardening
- Self-update: Pull latest changes and restart via CLI
- Dry-run mode: Test alert logic without sending notifications
- Production deployment: Installs to /opt with dedicated service user
- Startup configuration validation with clear error messages
- Service auto-start detection with warning alert
- Fully configurable via a single `.env` file

## Architecture

```mermaid
graph TD
    A[main.py CLI] --> B[Monitor Loop]
    B --> C[Sensor Manager]
    C --> D[CPU Sensor]
    C --> E[GPU Sensor]
    C --> F[DS18B20 Sensors]
    B --> G[Threshold Evaluator]
    G --> H[Notification Dispatcher]
    H --> I[Email Sender]
    H --> J[Webhook]
    H --> K[Telegram]
    H --> L[Pushover]
    H --> M[MQTT]
    B --> N[CSV Logger]
    B --> O[Fan Control]
    B --> P[Database Repository]
    A --> Q[Flask Dashboard]
    Q --> C
    Q --> R[REST API]
    Q --> S[Prometheus /metrics]
    Q --> T[Health Check]
```

## Monitoring Flow

```mermaid
sequenceDiagram
    participant M as Monitor
    participant S as Sensors
    participant T as Threshold Evaluator
    participant D as Dispatcher
    participant DB as Database
    participant L as Logger

    loop Every poll_interval seconds
        M->>S: read_all()
        S-->>M: SensorReading[]
        M->>L: log_temperature_csv()
        M->>DB: store_reading()
        M->>T: evaluate(sensor, temp)
        T-->>M: (new_level, previous_level)
        alt Level escalated or cooldown elapsed
            M->>D: dispatch_alert()
            D->>D: email, webhook, telegram, pushover, mqtt
            D->>DB: store_alert()
        end
        alt Recovered to normal
            M->>D: dispatch_recovery()
        end
    end
```

## Alert State Machine

```mermaid
stateDiagram-v2
    [*] --> NORMAL
    NORMAL --> WARNING: temp >= warning
    WARNING --> CRITICAL: temp >= critical OR escalation timeout
    CRITICAL --> EMERGENCY: temp >= emergency OR escalation timeout
    EMERGENCY --> CRITICAL: temp < emergency - hysteresis
    CRITICAL --> WARNING: temp < critical - hysteresis
    WARNING --> NORMAL: temp < warning - hysteresis
    NORMAL --> [*]
```

## Production Installation

The application installs to `/opt/pi-temp-alerter` with a dedicated system user, systemd service, and hardened file permissions.

### Prerequisites

- Raspberry Pi (any model) running Raspberry Pi OS
- Python 3.11 or later
- Git installed
- Network access (for sending emails)

### Install

```bash
# Clone the repository
git clone https://github.com/your-user/Pi-Temperature-Alerter.git
cd Pi-Temperature-Alerter

# Run the installer (requires root)
sudo ./install.sh
```

The installer will:

1. Create a dedicated `pi-temp-alerter` system user (no login shell)
2. Copy application files to `/opt/pi-temp-alerter`
3. Create a Python virtual environment and install dependencies
4. Set restrictive file permissions (`.env` is chmod 600)
5. Install and enable the systemd service
6. Create a `.env` from the template if one does not exist

### Post-Install Configuration

```bash
# Edit configuration
sudo nano /opt/pi-temp-alerter/.env

# Test email delivery
sudo -u pi-temp-alerter /opt/pi-temp-alerter/venv/bin/python /opt/pi-temp-alerter/main.py test-email

# Start the service
sudo systemctl start pi-temp-alerter

# Check status
sudo systemctl status pi-temp-alerter
```

### Uninstall

```bash
sudo ./uninstall.sh
```

The uninstaller will:

1. Stop and disable the systemd service
2. Remove the service file
3. Optionally preserve logs and data directories
4. Remove the application files from `/opt`
5. Remove the service user

### Updating

```bash
sudo /opt/pi-temp-alerter/venv/bin/python /opt/pi-temp-alerter/main.py update
```

Or from the cloned repository:

```bash
sudo python main.py update
```

The update command will:

1. Pull the latest changes via `git pull --ff-only`
2. Reinstall Python dependencies
3. Restart the systemd service if it is running

## Development Setup

For local development and testing (not production):

```bash
# Clone and enter the repository
git clone https://github.com/your-user/Pi-Temperature-Alerter.git
cd Pi-Temperature-Alerter

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create configuration
cp .env.example .env
nano .env

# Run directly
python main.py start
```

## CLI Reference

| Command       | Description                                          | Options                          |
|---------------|------------------------------------------------------|----------------------------------|
| `start`       | Start the monitoring daemon                          | -                                |
| `status`      | Show current sensor readings                         | -                                |
| `history`     | Display recent temperature history                   | `-n`, `--lines` (default: 20)   |
| `test-email`  | Send a test email to verify SMTP config              | -                                |
| `config`      | Display current configuration                        | -                                |
| `update`      | Pull latest changes and restart service (requires root) | -                             |

All commands are invoked via:

```bash
python main.py <command> [options]
```

Use `--help` on any command for usage details:

```bash
python main.py --help
python main.py history --help
```

## Configuration Reference

All configuration is managed through the `.env` file. Copy `.env.example` to `.env` and adjust.

### SMTP Settings

| Field           | Type   | Default          | Description                              |
|-----------------|--------|------------------|------------------------------------------|
| SMTP_HOST       | string | smtp.gmail.com   | SMTP server hostname                     |
| SMTP_PORT       | int    | 587              | SMTP server port                         |
| SMTP_USE_TLS    | bool   | true             | Enable STARTTLS                          |
| SMTP_USERNAME   | string | -                | SMTP authentication username             |
| SMTP_PASSWORD   | string | -                | SMTP authentication password/app key     |
| EMAIL_FROM      | string | -                | Sender address for outgoing emails       |

### Recipients

| Field                      | Type         | Default | Description                              |
|----------------------------|--------------|---------|------------------------------------------|
| EMAIL_RECIPIENTS_WARNING   | comma-list   | -       | Recipients for warning-level alerts      |
| EMAIL_RECIPIENTS_CRITICAL  | comma-list   | -       | Recipients for critical-level alerts     |
| EMAIL_RECIPIENTS_EMERGENCY | comma-list   | -       | Recipients for emergency-level alerts    |

### Temperature Thresholds

| Field           | Type  | Default | Description                                         |
|-----------------|-------|---------|-----------------------------------------------------|
| TEMP_WARNING    | float | 60.0    | Warning threshold in degrees Celsius                |
| TEMP_CRITICAL   | float | 70.0    | Critical threshold in degrees Celsius               |
| TEMP_EMERGENCY  | float | 80.0    | Emergency threshold in degrees Celsius              |
| TEMP_HYSTERESIS | float | 3.0     | Degrees below threshold before clearing alert state |

### Per-Sensor Threshold Overrides

Override thresholds for specific sensors using the pattern `TEMP_<LEVEL>_<SENSOR_NAME>`:

```
TEMP_WARNING_CPU=65
TEMP_CRITICAL_GPU=75
TEMP_WARNING_DS18B20_28_0000XXXX=25
```

### Monitoring

| Field                      | Type  | Default | Description                                                |
|----------------------------|-------|---------|------------------------------------------------------------|
| POLL_INTERVAL              | int   | 30      | Seconds between sensor readings                            |
| ALERT_COOLDOWN             | int   | 300     | Minimum seconds between repeated alerts                    |
| RECOVERY_NOTIFICATIONS     | bool  | true    | Send email when temperature returns to normal              |
| RATE_OF_CHANGE_THRESHOLD   | float | 0       | Alert if rising faster than this (C/min, 0 = disabled)     |
| ESCALATION_TIMEOUT         | int   | 0       | Seconds before auto-escalating (0 = disabled)              |
| DAILY_DIGEST_ENABLED       | bool  | false   | Enable daily summary email                                 |
| DAILY_DIGEST_HOUR          | int   | 7       | Hour (0-23) to send the daily digest                       |

### Sensors

| Field                 | Type   | Default                 | Description                            |
|-----------------------|--------|-------------------------|----------------------------------------|
| SENSOR_CPU_ENABLED    | bool   | true                    | Enable CPU temperature monitoring      |
| SENSOR_GPU_ENABLED    | bool   | true                    | Enable GPU temperature monitoring      |
| SENSOR_DS18B20_ENABLED| bool   | false                   | Enable DS18B20 one-wire sensors        |
| DS18B20_BASE_DIR      | string | /sys/bus/w1/devices     | Path to one-wire device directory      |

### Logging

| Field              | Type   | Default | Description                              |
|--------------------|--------|---------|------------------------------------------|
| LOG_LEVEL          | string | INFO    | Log level: DEBUG, INFO, WARNING, ERROR   |
| LOG_MAX_SIZE_MB    | int    | 10      | Max log file size before rotation (MB)   |
| LOG_BACKUP_COUNT   | int    | 5       | Number of rotated log files to keep      |
| CSV_LOGGING_ENABLED| bool   | true    | Enable CSV temperature history logging   |
| CSV_RETENTION_DAYS | int    | 30      | Days to retain CSV files before pruning  |

### Dashboard

| Field                  | Type   | Default   | Description                          |
|------------------------|--------|-----------|--------------------------------------|
| DASHBOARD_ENABLED      | bool   | true      | Enable the web dashboard             |
| DASHBOARD_HOST         | string | 0.0.0.0   | Dashboard bind address               |
| DASHBOARD_PORT         | int    | 5000      | Dashboard HTTP port                  |
| DASHBOARD_AUTH_ENABLED | bool   | false     | Enable HTTP Basic Auth               |
| DASHBOARD_USERNAME     | string | admin     | Basic auth username                  |
| DASHBOARD_PASSWORD     | string | -         | Basic auth password                  |
| ENDPOINT_API_ENABLED   | bool   | true      | Enable /api/* endpoints              |
| ENDPOINT_HEALTH_ENABLED| bool   | true      | Enable /api/health endpoint          |
| ENDPOINT_METRICS_ENABLED| bool  | true      | Enable /metrics Prometheus endpoint  |

### Database

| Field            | Type   | Default                          | Description                          |
|------------------|--------|----------------------------------|--------------------------------------|
| DATABASE_ENABLED | bool   | true                             | Enable database persistence          |
| DATABASE_URL     | string | sqlite:///data/pi_temp_alerter.db| SQLAlchemy connection URL            |

Supported database backends:

| Backend    | URL Format                                          | Driver Package    |
|------------|-----------------------------------------------------|-------------------|
| SQLite     | `sqlite:///data/pi_temp_alerter.db`                 | (built-in)        |
| MySQL      | `mysql+pymysql://user:pass@host:3306/dbname`        | `pip install pymysql` |
| PostgreSQL | `postgresql+psycopg2://user:pass@host:5432/dbname`  | `pip install psycopg2-binary` |

### Notifications

| Field               | Type   | Default            | Description                          |
|---------------------|--------|--------------------|--------------------------------------|
| WEBHOOK_ENABLED     | bool   | false              | Enable generic webhook notifications |
| WEBHOOK_URL         | string | -                  | URL to POST JSON alerts to           |
| TELEGRAM_ENABLED    | bool   | false              | Enable Telegram bot notifications    |
| TELEGRAM_BOT_TOKEN  | string | -                  | Telegram bot API token               |
| TELEGRAM_CHAT_ID    | string | -                  | Target chat/group ID                 |
| PUSHOVER_ENABLED    | bool   | false              | Enable Pushover notifications        |
| PUSHOVER_APP_TOKEN  | string | -                  | Pushover application token           |
| PUSHOVER_USER_KEY   | string | -                  | Pushover user/group key              |
| MQTT_ENABLED        | bool   | false              | Enable MQTT publishing               |
| MQTT_HOST           | string | localhost          | MQTT broker hostname                 |
| MQTT_PORT           | int    | 1883               | MQTT broker port                     |
| MQTT_USERNAME       | string | -                  | MQTT authentication username         |
| MQTT_PASSWORD       | string | -                  | MQTT authentication password         |
| MQTT_CLIENT_ID      | string | pi-temp-alerter    | MQTT client identifier               |
| MQTT_TOPIC_PREFIX   | string | pi-temp-alerter    | MQTT topic prefix                    |

### Fan Control

| Field               | Type  | Default | Description                              |
|---------------------|-------|---------|------------------------------------------|
| FAN_CONTROL_ENABLED | bool  | false   | Enable GPIO fan control                  |
| FAN_GPIO_PIN        | int   | 14      | BCM GPIO pin for fan transistor/relay    |
| FAN_ON_THRESHOLD    | float | 55.0    | Temperature to turn fan on               |
| FAN_OFF_THRESHOLD   | float | 45.0    | Temperature to turn fan off              |

### Advanced

| Field          | Type | Default | Description                                             |
|----------------|------|---------|---------------------------------------------------------|
| DRY_RUN        | bool | false   | Log alerts without actually sending them                |
| LOW_WRITE_MODE | bool | false   | Minimise SD card writes (see SD Card Longevity section) |

## SD Card Longevity

This application is designed to run 24/7 on a Raspberry Pi with an SD card. Several optimisations protect the card from excessive write wear:

- **Batched I/O**: All sensor readings from a poll cycle are written in a single file open (CSV) and a single database commit, rather than per-sensor
- **SQLite WAL mode**: Write-Ahead Logging uses sequential appends instead of rewriting the database file, dramatically reducing write amplification
- **Dashboard serves cached data**: API endpoints never trigger fresh sensor reads or disk I/O on HTTP requests
- **Log rotation**: Application logs are bounded at a configurable maximum size
- **CSV retention pruning**: Old CSV files are automatically deleted after the retention period

### Low-Write Mode

For maximum SD card longevity on always-on deployments, enable low-write mode:

```
LOW_WRITE_MODE=true
```

This automatically:

- Disables CSV logging (the database stores all readings instead, avoiding duplicate writes)
- Enforces a minimum 60-second poll interval (halves write operations vs the 30s default)
- Reduces log verbosity to WARNING level (eliminates routine INFO log writes)

### Write Budget

| Mode     | Writes/day | Data/day | SD card lifespan (32 GB) |
|----------|-----------|----------|-------------------------|
| Default  | ~5,900    | ~1.9 MB  | 14-43 years             |
| Low-write| ~2,900    | ~0.9 MB  | 30-85 years             |

### Manual Tuning

If you prefer fine-grained control without low-write mode:

- Set `CSV_LOGGING_ENABLED=false` if the database is sufficient for your history needs
- Increase `POLL_INTERVAL` to 60 or 120 seconds if real-time granularity is not needed
- Set `LOG_LEVEL=WARNING` to suppress routine informational log writes
- Use an external MySQL/PostgreSQL database (`DATABASE_URL`) to move all write I/O off the SD card entirely

## API Endpoints

| Endpoint           | Method | Toggle                    | Description                                      |
|--------------------|--------|---------------------------|--------------------------------------------------|
| `/`                | GET    | DASHBOARD_ENABLED         | Web dashboard UI                                 |
| `/api/current`     | GET    | ENDPOINT_API_ENABLED      | Current sensor readings and thresholds           |
| `/api/history`     | GET    | ENDPOINT_API_ENABLED      | Recent in-memory readings for charting           |
| `/api/history/csv` | GET    | ENDPOINT_API_ENABLED      | Last 500 entries from CSV logs                   |
| `/api/health`      | GET    | ENDPOINT_HEALTH_ENABLED   | System health, uptime, metrics, sensor status    |
| `/metrics`         | GET    | ENDPOINT_METRICS_ENABLED  | Prometheus exposition format metrics             |

## DS18B20 Sensor Setup

To use DS18B20 one-wire temperature sensors:

1. Connect the sensor data pin to GPIO4 (pin 7) with a 4.7k pull-up resistor to 3.3V
2. Enable the one-wire interface:

```bash
# Add to /boot/config.txt
dtoverlay=w1-gpio

# Reboot
sudo reboot
```

3. Verify the sensor is detected:

```bash
ls /sys/bus/w1/devices/28-*
```

4. Enable in `.env`:

```
SENSOR_DS18B20_ENABLED=true
```

## Gmail App Password Setup

If using Gmail as your SMTP provider:

1. Enable 2-Factor Authentication on your Google Account
2. Navigate to Google Account > Security > App passwords
3. Generate an app password for "Mail"
4. Use the generated 16-character password as `SMTP_PASSWORD` in `.env`

## MQTT and Home Assistant Integration

### Network Architecture

This application **pushes** data outbound to an MQTT broker. It does not require any inbound connections.

```mermaid
graph LR
    A[Pi Temperature Alerter] -->|TCP 1883 outbound| B[MQTT Broker]
    B --> C[Home Assistant]
    B --> D[Grafana]
    B --> E[Node-RED]
```

### Firewall Rules

If the Pi and Home Assistant are on different VLANs/subnets, you need one firewall rule:

| Source | Destination | Port | Protocol | Direction |
|--------|-------------|------|----------|----------|
| Pi IP  | HAOS IP     | 1883 | TCP      | Outbound from Pi |

For TLS-encrypted MQTT, use port 8883 instead.

No inbound rules are needed on the Pi - the MQTT command topic works over the same persistent outbound TCP connection.

### HAOS Mosquitto Setup

1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**
2. Install **Mosquitto broker**
3. Configure a user in **Settings > People > Users** (or use a local MQTT user)
4. Start the Mosquitto add-on
5. Note your HAOS IP address (e.g. `192.168.1.100`)

### Pi Configuration

Edit `.env` on the Pi:

```bash
MQTT_ENABLED=true
MQTT_HOST=192.168.1.100      # Your HAOS IP address
MQTT_PORT=1883
MQTT_USERNAME=mqtt_user       # The user you created in HAOS
MQTT_PASSWORD=mqtt_password
MQTT_CLIENT_ID=pi-temp-alerter
MQTT_TOPIC_PREFIX=pi-temp-alerter
```

Restart the service:

```bash
sudo systemctl restart pi-temp-alerter
```

### Verifying the Connection

Check the logs for a successful connection:

```bash
pi-temp-alerter logs | grep MQTT
# Should show: MQTT connected to 192.168.1.100:1883 (hostname: mypi, LWT enabled)
```

In Home Assistant, go to **Settings > Devices & Services > MQTT**. You should see a new device called "Pi Temp Alerter (hostname)" with all sensors auto-discovered.

### Topic Structure

All topics include the Pi's hostname for multi-device support:

| Topic | Content | Retained |
|-------|---------|----------|
| `pi-temp-alerter/<hostname>/sensor/<name>/state` | Temperature per sensor | Yes |
| `pi-temp-alerter/<hostname>/system/state` | Full system metrics (CPU, memory, disk, swap, load, network, processes, uptime) | Yes |
| `pi-temp-alerter/<hostname>/alerts` | Alert events with level and temperature | No |
| `pi-temp-alerter/<hostname>/recovery` | Recovery events | No |
| `pi-temp-alerter/<hostname>/status` | "online" / "offline" (LWT) | Yes |
| `pi-temp-alerter/<hostname>/command` | Inbound commands (subscribed) | - |

### Last Will and Testament (LWT)

If the Pi loses power or the process crashes, the MQTT broker automatically publishes `"offline"` to the status topic. Home Assistant marks all entities from this device as **unavailable** immediately without polling.

### Remote Commands

Publish JSON to `pi-temp-alerter/<hostname>/command` to remotely control the Pi:

```json
{"action": "test_alert"}              // Trigger a test alert
{"action": "status"}                  // Force republish online status
{"action": "reboot"}                  // Reboot the Pi
{"action": "poll_interval", "value": 60}  // Request interval change (logged)
```

You can send these from the Home Assistant MQTT integration, Node-RED, or any MQTT client.

### Home Assistant Automation Examples

Alert events are published with a `level` field that you can use in automations:

```yaml
# Flash a light red on emergency temperature
automation:
  - alias: "Pi Temperature Emergency"
    trigger:
      - platform: mqtt
        topic: "pi-temp-alerter/+/alerts"
    condition:
      - "{{ trigger.payload_json.level == 'EMERGENCY' }}"
    action:
      - service: light.turn_on
        target:
          entity_id: light.office_lamp
        data:
          color_name: red
          brightness: 255
      - service: notify.mobile_app
        data:
          title: "Pi Temperature Emergency"
          message: "{{ trigger.payload_json.hostname }}: {{ trigger.payload_json.temperature_c }} C"
```

```yaml
# Send HA notification on any alert
automation:
  - alias: "Pi Temperature Warning"
    trigger:
      - platform: mqtt
        topic: "pi-temp-alerter/+/alerts"
    action:
      - service: notify.persistent_notification
        data:
          title: "Pi Alert: {{ trigger.payload_json.level }}"
          message: "{{ trigger.payload_json.hostname }} sensor {{ trigger.payload_json.sensor }} at {{ trigger.payload_json.temperature_c }} C"
```

### Multi-Pi Setup

Multiple Pis can publish to the same broker. Each uses its own hostname in the topic path:

```
pi-temp-alerter/pi-living-room/sensor/cpu/state
pi-temp-alerter/pi-garage/sensor/cpu/state
pi-temp-alerter/pi-server/sensor/cpu/state
```

To aggregate in Grafana or Node-RED, subscribe to `pi-temp-alerter/+/system/state` (the `+` is a single-level wildcard). Each payload includes a `hostname` field for filtering.

In Home Assistant, each Pi appears as a separate device with its own entities.

### Grafana via MQTT

With the [Grafana MQTT datasource plugin](https://grafana.com/grafana/plugins/grafana-mqtt-datasource/):

1. Install the MQTT datasource plugin in Grafana
2. Add a new MQTT datasource pointing to your broker
3. Subscribe to `pi-temp-alerter/+/system/state`
4. The flat JSON payload maps directly to Grafana fields without transformation

### Node-RED Integration

Subscribe to topics with MQTT-in nodes:

- `pi-temp-alerter/+/alerts` - Process all alerts from all Pis
- `pi-temp-alerter/+/system/state` - Monitor system health across all Pis
- `pi-temp-alerter/specific-hostname/sensor/cpu/state` - Track a specific sensor

Use the `hostname` field in payloads to route, filter, or aggregate data.

## External Service Collectors

The application can auto-detect and publish statistics from co-hosted services via MQTT. This is useful for ADS-B feeder Pis running FlightRadar24 and readsb.

### Auto-Detection Behaviour

Collectors use a tri-state configuration:

| .env Setting | Behaviour |
|---|---|
| Not set (default) | Auto-detect: if the service is running and responds, publish its stats |
| `true` | Force enabled: always attempt collection (errors logged if service not found) |
| `false` | Explicitly disabled: never attempt collection even if service is present |

On your ADS-B Pi, you do not need to configure anything. If fr24feed and readsb are running, their stats will be automatically detected and published.

### Configuration

| Field | Type | Default | Description |
|---|---|---|---|
| COLLECTOR_FR24_ENABLED | bool/unset | (auto) | FlightRadar24 feed stats collection |
| COLLECTOR_READSB_ENABLED | bool/unset | (auto) | readsb ADS-B decoder stats collection |
| COLLECTOR_READSB_STATS_DIR | string | /run/readsb | Path to readsb JSON stats directory |

### FlightRadar24 (fr24feed)

Collects from fr24feed's local HTTP monitor endpoint (`http://127.0.0.1:8754/monitor.json`), falling back to the `fr24feed-status` CLI command.

MQTT topic: `pi-temp-alerter/<hostname>/service/fr24feed/state`

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

### readsb ADS-B Decoder

Reads JSON statistics from readsb's run directory (`/run/readsb/stats.json` and `/run/readsb/aircraft.json`).

MQTT topic: `pi-temp-alerter/<hostname>/service/readsb/state`

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

### Disabling Auto-Detection

To prevent a collector from running even when the service is present:

```bash
# Disable fr24feed stats (service still runs, just not monitored)
COLLECTOR_FR24_ENABLED=false

# Disable readsb stats
COLLECTOR_READSB_ENABLED=false
```

### All Available Collectors

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

### NTP / Chrony

Auto-detects chrony (preferred) or ntpd and publishes time synchronisation health.

MQTT topic: `pi-temp-alerter/<hostname>/service/ntp/state`

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

### GPS (gpsd)

Auto-detects gpsd by connecting to its default TCP port (2947). Useful for ADS-B feeders that use GPS for MLAT synchronisation.

MQTT topic: `pi-temp-alerter/<hostname>/service/gps/state`

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

## Project Structure

```
Pi-Temperature-Alerter/
|-- main.py                  # CLI entry point
|-- requirements.txt         # Python dependencies
|-- install.sh               # Production installer (requires root)
|-- uninstall.sh             # Clean removal script (requires root)
|-- .env.example             # Configuration template
|-- SECURITY.md              # Security policy and guidance
|-- CONTRIBUTING.md          # Contribution guidelines
|-- LICENCE                  # MIT licence
|-- systemd/
|   `-- pi-temp-alerter.service  # Systemd unit file
`-- src/
    |-- config.py            # Configuration loader and validation
    |-- logger.py            # Logging and CSV setup with daily rotation
    |-- monitor.py           # Core monitoring loop
    |-- sensors/
    |   |-- base.py          # Sensor interface
    |   |-- cpu.py           # CPU temperature sensor
    |   |-- gpu.py           # GPU temperature sensor
    |   |-- ds18b20.py       # DS18B20 one-wire sensor
    |   |-- manager.py       # Sensor orchestration
    |   |-- system_metrics.py # CPU/memory/disk/throttle metrics
    |   `-- fan_control.py   # GPIO fan control
    |-- alerting/
    |   |-- thresholds.py    # Threshold evaluation and hysteresis
    |   |-- email_sender.py  # SMTP email dispatch (plain + HTML)
    |   |-- dispatcher.py    # Multi-channel notification fan-out
    |   |-- digest.py        # Daily summary email
    |   `-- notifiers/
    |       |-- webhook.py   # Generic HTTP webhook
    |       |-- telegram.py  # Telegram Bot API
    |       |-- pushover.py  # Pushover push notifications
    |       `-- mqtt.py      # MQTT publishing
    |-- database/
    |   |-- models.py        # SQLAlchemy models and engine setup
    |   `-- repository.py    # Query and persistence helpers
    `-- dashboard/
        |-- app.py           # Flask web application
        `-- templates/
            `-- index.html   # Dashboard UI template
```

## Licence

MIT - see [LICENCE](LICENCE) for full text.
