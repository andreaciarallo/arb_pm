#!/usr/bin/env bash
# setup_vps.sh — Bootstrap a fresh Ubuntu 22.04 VPS for the Polymarket Arbitrage Bot
#
# Usage (run as root on the new VPS):
#   curl -fsSL https://raw.githubusercontent.com/andreaciarallo/arb_pm/master/scripts/setup_vps.sh | bash
#
# Or after cloning:
#   bash scripts/setup_vps.sh
#
# What this does:
#   1. Update apt and install required system packages
#   2. Install Docker CE (official docker.com method, not snap)
#   3. Add current user to the docker group
#   4. Clone the repo to /opt/arbbot
#   5. Print next steps
#
# Requirements:
#   - Ubuntu 22.04 LTS (not tested on other distros)
#   - Run as root (or user with sudo)
#   - Outbound internet access on ports 80, 443

set -euo pipefail

# ── Color helpers ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[setup]${NC} $*"; }
err()  { echo -e "${RED}[setup] ERROR:${NC} $*" >&2; exit 1; }

# ── Config ─────────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/andreaciarallo/arb_pm.git"
REPO_BRANCH="master"
INSTALL_DIR="/opt/arbbot"

# ── Preflight checks ───────────────────────────────────────────────────────────
if [[ "$EUID" -ne 0 ]]; then
  err "This script must be run as root. Try: sudo bash setup_vps.sh"
fi

log "Starting VPS bootstrap for Polymarket Arbitrage Bot..."
log "Target install directory: $INSTALL_DIR"

# ── Step 1: System packages ────────────────────────────────────────────────────
log "Step 1/4 — Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
  git \
  curl \
  ca-certificates \
  gnupg \
  lsb-release

# ── Step 2: Install Docker CE ──────────────────────────────────────────────────
log "Step 2/4 — Installing Docker CE..."

# Remove any old/conflicting Docker packages (ignore errors if not present)
apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Add Docker's official GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker CE + Compose plugin
apt-get update -qq
apt-get install -y --no-install-recommends \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

# Verify installation
DOCKER_VERSION=$(docker --version)
log "Docker installed: $DOCKER_VERSION"

# Enable and start Docker daemon
systemctl enable docker
systemctl start docker

# ── Step 3: Add user to docker group ──────────────────────────────────────────
log "Step 3/4 — Configuring docker group..."

# Add root to docker group (enables running docker without sudo in new shells)
usermod -aG docker root

# If a non-root SUDO_USER exists, add them too
if [[ -n "${SUDO_USER:-}" ]] && [[ "$SUDO_USER" != "root" ]]; then
  usermod -aG docker "$SUDO_USER"
  log "Added $SUDO_USER to docker group."
fi

warn "Docker group membership takes effect in new shell sessions."
warn "If 'docker run' fails with permission denied, run: newgrp docker"

# ── Step 4: Clone repo ─────────────────────────────────────────────────────────
log "Step 4/4 — Cloning repository..."

if [[ -d "$INSTALL_DIR/.git" ]]; then
  warn "Repo already exists at $INSTALL_DIR. Pulling latest..."
  git -C "$INSTALL_DIR" pull --ff-only origin "$REPO_BRANCH"
else
  git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
  log "Repo cloned to $INSTALL_DIR"
fi

# Set ownership (root owns the dir, no special perms needed for Docker)
chown -R root:root "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
log "Setup complete. Next steps:"
echo ""
echo "  1. cd $INSTALL_DIR"
echo ""
echo "  2. Transfer secrets.env from old VPS (from your LOCAL machine):"
echo "       scp root@OLD_VPS_IP:/opt/arbbot/secrets.env root@\$(hostname -I | awk '{print \$1}'):/opt/arbbot/secrets.env"
echo "       chmod 600 $INSTALL_DIR/secrets.env"
echo ""
echo "  3. Build and start the bot:"
echo "       docker compose build bot"
echo "       docker compose up -d"
echo ""
echo "  4. Verify bot is healthy:"
echo "       docker compose ps     # status should show (healthy)"
echo "       docker compose logs --tail=30"
echo ""
echo "  5. Run verification checks (see DEPLOY.md for full details):"
echo "       curl -s https://polymarket.com/api/geoblock | python3 -m json.tool"
echo "       docker compose exec bot python scripts/benchmark_latency.py"
echo ""
echo "See DEPLOY.md for full migration guide including UAT verification and"
echo "old VPS decommission steps."
