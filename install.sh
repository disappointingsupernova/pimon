#!/usr/bin/env bash
# install.sh - Install Pi Temperature Alerter to /opt/pi-temp-alerter
# Must be run as root (sudo ./install.sh)
#
# This script is idempotent - safe to run multiple times. It will:
#   - Skip steps that are already complete
#   - Preserve existing configuration
#   - Update application files on reinstall

set -euo pipefail

APP_NAME="pi-temp-alerter"
INSTALL_DIR="/opt/${APP_NAME}"
SERVICE_USER="${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# If the repo is already under /opt, install in-place rather than copying
# to a separate directory. This avoids path mismatches from repo naming.
if [[ "${REPO_DIR}" == /opt/* ]]; then
    INSTALL_DIR="${REPO_DIR}"
fi

# Colour output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# =============================================================================
# Pre-flight checks
# =============================================================================

if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo ./install.sh"
fi

# Check for Python 3
if ! command -v python3 &>/dev/null; then
    error "Python 3 is required but not found. Install with: apt install python3"
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED="3.11"
if [[ "$(printf '%s\n' "$REQUIRED" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED" ]]; then
    error "Python ${REQUIRED}+ is required. Found: ${PYTHON_VERSION}"
fi

# =============================================================================
# Install OS-level dependencies if missing
# =============================================================================

PACKAGES_NEEDED=()

# python3-venv is required to create virtual environments
if ! python3 -c "import ensurepip" &>/dev/null; then
    PACKAGES_NEEDED+=("python3.${PYTHON_VERSION##*.}-venv")
    # Fall back to generic package name if version-specific doesn't exist
    if ! apt-cache show "python3.${PYTHON_VERSION##*.}-venv" &>/dev/null 2>&1; then
        PACKAGES_NEEDED=("python3-venv")
    fi
fi

# pip may not be installed on minimal systems
if ! python3 -c "import pip" &>/dev/null; then
    PACKAGES_NEEDED+=("python3-pip")
fi

# git is needed for the update command
if ! command -v git &>/dev/null; then
    PACKAGES_NEEDED+=("git")
fi

if [[ ${#PACKAGES_NEEDED[@]} -gt 0 ]]; then
    info "Installing required OS packages: ${PACKAGES_NEEDED[*]}"
    apt-get update -qq
    apt-get install -y -qq "${PACKAGES_NEEDED[@]}"
fi

# =============================================================================
# Installation
# =============================================================================

info "Installing ${APP_NAME} to ${INSTALL_DIR}"

# Create service user (no login shell, no home directory)
if ! id "${SERVICE_USER}" &>/dev/null; then
    info "Creating service user: ${SERVICE_USER}"
    useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
else
    info "Service user already exists: ${SERVICE_USER}"
fi

# Create install directory structure
info "Creating install directory"
mkdir -p "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}/logs"
mkdir -p "${INSTALL_DIR}/data"

# Copy application files (skip if installing in-place from the repo itself)
if [[ "${REPO_DIR}" != "${INSTALL_DIR}" ]]; then
    info "Copying application files"
    rm -rf "${INSTALL_DIR}/src"
    cp -r "${REPO_DIR}/src" "${INSTALL_DIR}/"
    cp "${REPO_DIR}/main.py" "${INSTALL_DIR}/"
    cp "${REPO_DIR}/requirements.txt" "${INSTALL_DIR}/"
else
    info "Installing in-place (repo is the install directory)"
fi

# Copy .env only if it does not already exist (preserve existing config)
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
    cp "${REPO_DIR}/.env.example" "${INSTALL_DIR}/.env"
    info "Created .env from template - edit ${INSTALL_DIR}/.env with your settings"
else
    info "Existing .env preserved (not overwritten)"
fi

# Create or update the virtual environment
# Verify existing venv is functional (may be broken from a failed install)
if [[ -d "${INSTALL_DIR}/venv" ]] && [[ -x "${INSTALL_DIR}/venv/bin/python" ]]; then
    info "Virtual environment already exists, updating"
else
    # Remove broken venv if it exists but is non-functional
    if [[ -d "${INSTALL_DIR}/venv" ]]; then
        warn "Existing virtual environment is broken, recreating"
        rm -rf "${INSTALL_DIR}/venv"
    fi
    info "Creating Python virtual environment"
    python3 -m venv "${INSTALL_DIR}/venv"
fi

info "Installing Python dependencies"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip --quiet
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" --quiet

# Set ownership and permissions
info "Setting file permissions"
# The service user needs to own the writable directories (logs, data)
# and be able to read the application files
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/logs"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/data"
chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/.env"
chmod 600 "${INSTALL_DIR}/.env"
# Ensure the service user can read application files
chmod -R o+rX "${INSTALL_DIR}/src" "${INSTALL_DIR}/main.py" "${INSTALL_DIR}/requirements.txt"
# Ensure venv is accessible by the service user
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/venv"

# Install systemd service (generate from template with correct paths)
info "Installing systemd service"
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Pi Temperature Alerter - System health monitoring
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python main.py start
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
ProtectHome=true
PrivateTmp=true
ReadWritePaths=${INSTALL_DIR}/logs ${INSTALL_DIR}/data

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload

# Enable the service (idempotent - harmless if already enabled)
if ! systemctl is-enabled --quiet "${APP_NAME}" 2>/dev/null; then
    systemctl enable "${APP_NAME}"
    info "Service enabled for auto-start"
else
    info "Service already enabled"
fi

# Install CLI shortcut symlink to /usr/local/bin
CLI_LINK="/usr/local/bin/${APP_NAME}"
CLI_TARGET="${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/main.py"

# Create a wrapper script (symlinks don't work well with venv python paths)
info "Installing CLI shortcut: ${CLI_LINK}"
cat > "${CLI_LINK}" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/venv/bin/python" "${INSTALL_DIR}/main.py" "\$@"
EOF
chmod 755 "${CLI_LINK}"

# =============================================================================
# Done
# =============================================================================

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
