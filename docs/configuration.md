# Configuration Reference

All configuration is managed through the `.env` file. Copy `.env.example` to `.env` and adjust.

## SMTP Settings

| Field           | Type   | Default          | Description                              |
|-----------------|--------|------------------|------------------------------------------|
| SMTP_HOST       | string | smtp.gmail.com   | SMTP server hostname                     |
| SMTP_PORT       | int    | 587              | SMTP server port                         |
| SMTP_USE_TLS    | bool   | true             | Enable STARTTLS                          |
| SMTP_USERNAME   | string | -                | SMTP authentication username             |
| SMTP_PASSWORD   | string | -                | SMTP authentication password/app key     |
| EMAIL_FROM      | string | -                | Sender address for outgoing emails       |

## Recipients

| Field                      | Type         | Default | Description                              |
|----------------------------|--------------|---------|------------------------------------------|
| EMAIL_RECIPIENTS_WARNING   | comma-list   | -       | Recipients for warning-level alerts      |
| EMAIL_RECIPIENTS_CRITICAL  | comma-list   | -       | Recipients for critical-level alerts     |
| EMAIL_RECIPIENTS_EMERGENCY | comma-list   | -       | Recipients for emergency-level alerts    |

## Temperature Thresholds

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

## Monitoring

| Field                      | Type  | Default | Description                                                |
|----------------------------|-------|---------|------------------------------------------------------------|
| POLL_INTERVAL              | int   | 30      | Seconds between sensor readings                            |
| ALERT_COOLDOWN             | int   | 300     | Minimum seconds between repeated alerts                    |
| RECOVERY_NOTIFICATIONS     | bool  | true    | Send email when temperature returns to normal              |
| RATE_OF_CHANGE_THRESHOLD   | float | 0       | Alert if rising faster than this (C/min, 0 = disabled)     |
| ESCALATION_TIMEOUT         | int   | 0       | Seconds before auto-escalating (0 = disabled)              |
| DAILY_DIGEST_ENABLED       | bool  | false   | Enable daily summary email                                 |
| DAILY_DIGEST_HOUR          | int   | 7       | Hour (0-23) to send the daily digest                       |

## Sensors

| Field                 | Type   | Default                 | Description                            |
|-----------------------|--------|-------------------------|----------------------------------------|
| SENSOR_CPU_ENABLED    | bool   | true                    | Enable CPU temperature monitoring      |
| SENSOR_GPU_ENABLED    | bool   | true                    | Enable GPU temperature monitoring      |
| SENSOR_DS18B20_ENABLED| bool   | false                   | Enable DS18B20 one-wire sensors        |
| DS18B20_BASE_DIR      | string | /sys/bus/w1/devices     | Path to one-wire device directory      |

## Logging

| Field              | Type   | Default | Description                              |
|--------------------|--------|---------|------------------------------------------|
| LOG_LEVEL          | string | INFO    | Log level: DEBUG, INFO, WARNING, ERROR   |
| LOG_MAX_SIZE_MB    | int    | 10      | Max log file size before rotation (MB)   |
| LOG_BACKUP_COUNT   | int    | 5       | Number of rotated log files to keep      |
| CSV_LOGGING_ENABLED| bool   | true    | Enable CSV temperature history logging   |
| CSV_RETENTION_DAYS | int    | 30      | Days to retain CSV files before pruning  |

## Dashboard

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

## Database

| Field            | Type   | Default                          | Description                          |
|------------------|--------|----------------------------------|--------------------------------------|
| DATABASE_ENABLED | bool   | true                             | Enable database persistence          |
| DATABASE_URL     | string | sqlite:///data/pimon.db          | SQLAlchemy connection URL            |

Supported database backends:

| Backend    | URL Format                                          | Driver Package    |
|------------|-----------------------------------------------------|-------------------|
| SQLite     | `sqlite:///data/pimon.db`                           | (built-in)        |
| MySQL      | `mysql+pymysql://user:pass@host:3306/dbname`        | `pip install pymysql` |
| PostgreSQL | `postgresql+psycopg2://user:pass@host:5432/dbname`  | `pip install psycopg2-binary` |

## Notifications

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
| MQTT_CLIENT_ID      | string | pimon              | MQTT client identifier               |
| MQTT_TOPIC_PREFIX   | string | pimon              | MQTT topic prefix                    |

## Fan Control

| Field               | Type  | Default | Description                              |
|---------------------|-------|---------|------------------------------------------|
| FAN_CONTROL_ENABLED | bool  | false   | Enable GPIO fan control                  |
| FAN_GPIO_PIN        | int   | 14      | BCM GPIO pin for fan transistor/relay    |
| FAN_ON_THRESHOLD    | float | 55.0    | Temperature to turn fan on               |
| FAN_OFF_THRESHOLD   | float | 45.0    | Temperature to turn fan off              |

## Advanced

| Field          | Type | Default | Description                                             |
|----------------|------|---------|---------------------------------------------------------|
| DRY_RUN        | bool | false   | Log alerts without actually sending them                |
| LOW_WRITE_MODE | bool | false   | Minimise SD card writes (see [SD Card Longevity](sd-card-longevity.md)) |

## Gmail App Password Setup

If using Gmail as your SMTP provider:

1. Enable 2-Factor Authentication on your Google Account
2. Navigate to Google Account > Security > App passwords
3. Generate an app password for "Mail"
4. Use the generated 16-character password as `SMTP_PASSWORD` in `.env`
