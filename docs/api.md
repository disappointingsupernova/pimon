# API Endpoints

## Available Endpoints

| Endpoint           | Method | Toggle                    | Description                                      |
|--------------------|--------|---------------------------|--------------------------------------------------|
| `/`                | GET    | DASHBOARD_ENABLED         | Web dashboard UI                                 |
| `/api/current`     | GET    | ENDPOINT_API_ENABLED      | Current sensor readings and thresholds           |
| `/api/history`     | GET    | ENDPOINT_API_ENABLED      | Recent in-memory readings for charting           |
| `/api/history/csv` | GET    | ENDPOINT_API_ENABLED      | Last 500 entries from CSV logs                   |
| `/api/health`      | GET    | ENDPOINT_HEALTH_ENABLED   | System health, uptime, metrics, sensor status    |
| `/metrics`         | GET    | ENDPOINT_METRICS_ENABLED  | Prometheus exposition format metrics             |

## Prometheus Metrics

The `/metrics` endpoint exposes data in Prometheus text exposition format, suitable for scraping by Prometheus or compatible tools (e.g. Grafana Agent, Victoria Metrics).

Configure your Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: pimon
    static_configs:
      - targets: ['your-pi-ip:5000']
```

## Authentication

If `DASHBOARD_AUTH_ENABLED=true`, all endpoints require HTTP Basic Auth. Include credentials in your scrape config or API calls:

```yaml
scrape_configs:
  - job_name: pimon
    basic_auth:
      username: admin
      password: your_password
    static_configs:
      - targets: ['your-pi-ip:5000']
```

## Rate Limiting

All endpoints are rate-limited to 60 requests per IP with a token-bucket algorithm (refills at 1 token/second). Exceeding this returns HTTP 429.
