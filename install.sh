#!/usr/bin/env bash
# install.sh - Install Pi Temperature Alerter to /opt/pi-temp-alerter
# Must be run as root (sudo ./install.sh)

set -euo pipefail

APP_NAME="pi-temp-alerter"
INSTALL_DIR="/opt/${APP_NAME}"
SERVICE_USER="${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colour output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# Pre-flight checks
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo ./install.sh"
fi

if ! command -v python3 &>/dev/null; then
    error "Python 3 is required but not found."
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED="3.11"
if [[ "$(printf '%s\n' "$REQUIRED" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED" ]]; then
    error "Python ${REQUIRED}+ is required. Found: ${PYTHON_VERSION}"
fi

info "Installing ${APP_NAME} to ${INSTALL_DIR}"

# Create service user (no login shell, no home directory)
if ! id "${SERVICE_USER}" &>/dev/null; then
    info "Creating service user: ${SERVICE_USER}"
    useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

# Create install directory
info "Creating install directory"
mkdir -p "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}/logs"
mkdir -p "${INSTALL_DIR}/data"

# Copy application files
info "Copying application files"
cp -r "${REPO_DIR}/src" "${INSTALL_DIR}/"
cp "${REPO_DIR}/main.py" "${INSTALL_DIR}/"
cp "${REPO_DIR}/requirements.txt" "${INSTALL_DIR}/"

# Copy .env if it does not already exist (preserve existing config on reinstall)
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
    cp "${REPO_DIR}/.env.example" "${INSTALL_DIR}/.env"
    info "Created .env from template - edit ${INSTALL_DIR}/.env with your settings"
else
    info "Existing .env preserved (not overwritten)"
fi

# Create virtual environment and install dependencies
info "Setting up Python virtual environment"
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip --quiet
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" --quiet

# Set ownership
info "Setting file permissions"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 600 "${INSTALL_DIR}/.env"

# Install systemd service
info "Installing systemd service"
cp "${REPO_DIR}/systemd/${APP_NAME}.service" "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable "${APP_NAME}"

info "Installation complete."
echo ""
echo "  Install location: ${INSTALL_DIR}"
echo "  Configuration:    ${INSTALL_DIR}/.env"
echo "  Service:          ${APP_NAME}.service"
echo ""
echo "Next steps:"
echo "  1. Edit configuration: sudo nano ${INSTALL_DIR}/.env"
echo "  2. Test email:         sudo -u ${SERVICE_USER} ${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/main.py test-email"
echo "  3. Start service:      sudo systemctl start ${APP_NAME}"
echo "  4. Check status:       sudo systemctl status ${APP_NAME}"
