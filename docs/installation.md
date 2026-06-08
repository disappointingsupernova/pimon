# Installation

## Quick Start

```bash
git clone https://github.com/disappointingsupernova/pimon
cd pimon
sudo ./install.sh
sudo nano /opt/pimon/.env
sudo systemctl start pimon
```

Then open `http://your-pi-ip:5000` in a browser.

## Prerequisites

- Raspberry Pi (any model) running Raspberry Pi OS
- Python 3.11 or later
- Git installed
- Network access (for sending emails)

## Production Installation

The application installs to `/opt/pimon` with a dedicated system user, systemd service, and hardened file permissions.

```bash
git clone https://github.com/disappointingsupernova/pimon.git
cd pimon
sudo ./install.sh
```

The installer will:

1. Create a dedicated `pimon` system user (no login shell)
2. Copy application files to `/opt/pimon`
3. Create a Python virtual environment and install dependencies
4. Set restrictive file permissions (`.env` is chmod 600)
5. Install and enable the systemd service
6. Create a `.env` from the template if one does not exist

### Post-Install Configuration

```bash
sudo nano /opt/pimon/.env
sudo -u pimon /opt/pimon/venv/bin/python /opt/pimon/main.py test-email
sudo systemctl start pimon
sudo systemctl status pimon
```

## Development Setup

For local development and testing (not production):

```bash
git clone https://github.com/disappointingsupernova/pimon.git
cd pimon
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py start
```

## Updating

```bash
sudo /opt/pimon/venv/bin/python /opt/pimon/main.py update
```

Or from the cloned repository:

```bash
sudo python main.py update
```

The update command will:

1. Pull the latest changes via `git pull --ff-only`
2. Reinstall Python dependencies
3. Restart the systemd service if it is running

## Uninstalling

```bash
sudo ./uninstall.sh
```

The uninstaller will:

1. Stop and disable the systemd service
2. Remove the service file
3. Optionally preserve logs and data directories
4. Remove the application files from `/opt`
5. Remove the service user
