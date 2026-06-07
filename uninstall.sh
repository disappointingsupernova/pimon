#!/usr/bin/env bash
# uninstall.sh - Remove Pi Temperature Alerter from the system
# Must be run as root (sudo ./uninstall.sh)

set -euo pipefail

APP_NAME="pi-temp-alerter"
INSTALL_DIR="/opt/${APP_NAME}"
SERVICE_USER="${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo ./uninstall.sh"
fi

echo "This will remove Pi Temperature Alerter from the system."
echo "  Install directory: ${INSTALL_DIR}"
echo "  Service:           ${APP_NAME}.service"
echo "  User:              ${SERVICE_USER}"
echo ""
read -rp "Are you sure you want to continue? [y/N] " confirm
if [[ "${confirm}" != [yY] ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

# Stop and disable the service
if systemctl is-active --quiet "${APP_NAME}" 2>/dev/null; then
    info "Stopping ${APP_NAME} service"
    systemctl stop "${APP_NAME}"
fi

if systemctl is-enabled --quiet "${APP_NAME}" 2>/dev/null; then
    info "Disabling ${APP_NAME} service"
    systemctl disable "${APP_NAME}"
fi

# Remove service file
if [[ -f "${SERVICE_FILE}" ]]; then
    info "Removing systemd service file"
    rm -f "${SERVICE_FILE}"
    systemctl daemon-reload
fi

# Remove install directory
if [[ -d "${INSTALL_DIR}" ]]; then
    # Offer to preserve data and logs
    read -rp "Preserve logs and data? [Y/n] " keep_data
    if [[ "${keep_data}" == [nN] ]]; then
        info "Removing ${INSTALL_DIR} (including logs and data)"
        rm -rf "${INSTALL_DIR}"
    else
        info "Removing application files (preserving logs/ and data/)"
        find "${INSTALL_DIR}" -mindepth 1 -maxdepth 1 \
            ! -name "logs" ! -name "data" -exec rm -rf {} +
        warn "Logs and data retained at ${INSTALL_DIR}/"
    fi
fi

# Remove service user
if id "${SERVICE_USER}" &>/dev/null; then
    info "Removing service user: ${SERVICE_USER}"
    userdel "${SERVICE_USER}" 2>/dev/null || true
fi

info "Uninstall complete."
