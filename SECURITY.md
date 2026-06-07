# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | Yes                |
| older   | No                 |

Only the latest version on the `main` branch receives security updates. Please ensure you are running the most recent release.

## Reporting a Vulnerability

If you discover a security vulnerability in Pi Temperature Alerter, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities.
2. Email the maintainer directly at the address listed in the repository's profile.
3. Include a clear description of the vulnerability, steps to reproduce, and the potential impact.
4. You will receive an acknowledgement within 48 hours.
5. A fix will be developed privately and released as soon as possible.

## Security Considerations

### Credentials and Secrets

- The `.env` file contains sensitive credentials (SMTP passwords, API tokens, database URLs). It is excluded from version control via `.gitignore`.
- The production installer (`install.sh`) sets `.env` permissions to `chmod 600`, readable only by the service user.
- Never commit `.env` to the repository. Only `.env.example` (with placeholder values) is tracked.
- Database URLs may contain credentials - ensure `DATABASE_URL` is kept in `.env` and not logged.

### Network Exposure

- The Flask dashboard binds to `0.0.0.0` by default, exposing it to the local network. A warning is logged on startup if authentication is not enabled.
- Enable `DASHBOARD_AUTH_ENABLED=true` with a strong password if the Pi is accessible on an untrusted network.
- Authentication uses timing-safe (`hmac.compare_digest`) comparisons to prevent credential guessing via timing attacks.
- Consider placing the dashboard behind a reverse proxy (nginx, Caddy) with HTTPS for production use.
- Individual endpoints (`/api/*`, `/metrics`, `/api/health`) can be disabled via `ENDPOINT_*_ENABLED` settings.
- All user-derived values (sensor names) are escaped before being rendered in HTML templates, emails, and Prometheus metrics to prevent injection.

### Service Hardening

The systemd service file includes several security features:

- `NoNewPrivileges=true` - Prevents privilege escalation
- `ProtectSystem=strict` - Read-only filesystem except allowed paths
- `ProtectHome=true` - No access to home directories
- `PrivateTmp=true` - Isolated temporary directory
- Runs as a dedicated `pi-temp-alerter` system user with no login shell

### Database Security

- SQLite databases are stored in the `data/` directory with restrictive permissions.
- For MySQL/PostgreSQL, use a dedicated database user with minimal privileges (SELECT, INSERT, DELETE on application tables only).
- Do not use the database root account in `DATABASE_URL`.
- Ensure database connections use TLS in production where possible.

### SMTP Security

- Use application-specific passwords (e.g. Gmail App Passwords) rather than your primary account password.
- Enable TLS (`SMTP_USE_TLS=true`) to encrypt email traffic in transit.
- SMTP credentials are never logged, even in debug mode.

### MQTT Security

- Use TLS-enabled MQTT brokers in production.
- Use dedicated MQTT credentials with limited publish/subscribe permissions.
- The MQTT password is never logged.

### Webhook Security

- SSL certificate verification is enabled by default for all webhook URLs.
- Set `WEBHOOK_VERIFY_SSL=false` only for internal endpoints with self-signed certificates.
- Webhook URLs are treated as secrets and never exposed via the dashboard or API.

### Third-Party Notifications

- Webhook URLs, Telegram bot tokens, and Pushover keys should be treated as secrets.
- These are stored only in `.env` and never exposed via the dashboard or API.
- The `/api/health` endpoint does not expose any credentials or tokens.

## Dependencies

Keep dependencies up to date to avoid known vulnerabilities:

```bash
pip install --upgrade -r requirements.txt
```

Review the dependency list periodically:

- `python-dotenv` - Environment variable loading
- `flask` - Web dashboard framework
- `paho-mqtt` - MQTT client
- `sqlalchemy` - Database ORM
- `pymysql` / `psycopg2` - Optional database drivers

## Responsible Disclosure

We follow responsible disclosure practices. Security researchers who report valid vulnerabilities will be acknowledged in the project's changelog (with permission).
