#!/usr/bin/env bash
# setup-vps.sh — Baseline VPS hardening and Docker/Compose installation
# Tested on Ubuntu 22.04 LTS and Ubuntu 24.04 LTS.
# Run as root (or via sudo) on a freshly provisioned VPS:
#   sudo bash setup-vps.sh [--deploy-user <username>]
#
# What this script does:
#   1. Full system update
#   2. Create a non-root deploy user with sudo access (optional)
#   3. Configure SSH hardening
#   4. Set up UFW firewall
#   5. Install and configure fail2ban
#   6. Configure time synchronisation (systemd-timesyncd / chrony)
#   7. Install Docker Engine and Docker Compose plugin
#   8. Enable automatic security updates
#   9. Tune kernel parameters for production

set -euo pipefail

# ── Helpers ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

require_root() { [[ $EUID -eq 0 ]] || err "This script must be run as root."; }

# ── Argument parsing ──────────────────────────────────────────────────────────
DEPLOY_USER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-user) DEPLOY_USER="$2"; shift 2 ;;
    *) err "Unknown argument: $1" ;;
  esac
done

require_root

# ── 1. System update ──────────────────────────────────────────────────────────
log "Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get autoremove -y
apt-get autoclean -y

# ── 2. Essential packages ─────────────────────────────────────────────────────
log "Installing essential packages..."
apt-get install -y \
  curl wget git unzip ca-certificates gnupg lsb-release \
  ufw fail2ban chrony \
  htop iotop net-tools nmap ncdu \
  logrotate rsync jq

# ── 3. Create deploy user ─────────────────────────────────────────────────────
if [[ -n "$DEPLOY_USER" ]]; then
  if id "$DEPLOY_USER" &>/dev/null; then
    warn "User '$DEPLOY_USER' already exists — skipping creation."
  else
    log "Creating deploy user: $DEPLOY_USER"
    useradd -m -s /bin/bash "$DEPLOY_USER"
    usermod -aG sudo "$DEPLOY_USER"
    # Prompt for password
    passwd "$DEPLOY_USER"
    log "Add your SSH public key to /home/$DEPLOY_USER/.ssh/authorized_keys"
  fi
fi

# ── 4. SSH hardening ──────────────────────────────────────────────────────────
log "Hardening SSH configuration..."
SSHD_CONFIG=/etc/ssh/sshd_config

cp "$SSHD_CONFIG" "${SSHD_CONFIG}.bak.$(date +%F)"

# Apply settings idempotently
declare -A SSH_SETTINGS=(
  [PermitRootLogin]="no"
  [PasswordAuthentication]="no"
  [PubkeyAuthentication]="yes"
  [X11Forwarding]="no"
  [MaxAuthTries]="3"
  [ClientAliveInterval]="300"
  [ClientAliveCountMax]="2"
  [LoginGraceTime]="30"
  [AllowAgentForwarding]="no"
  [AllowTcpForwarding]="no"
  # Note: "Protocol 2" is the only supported protocol in OpenSSH >= 7.4
  # (Ubuntu 22.04+); the Protocol directive was removed from sshd_config
  # and does not need to be set explicitly.
)

for key in "${!SSH_SETTINGS[@]}"; do
  val="${SSH_SETTINGS[$key]}"
  if grep -q "^${key}" "$SSHD_CONFIG"; then
    sed -i "s|^${key}.*|${key} ${val}|" "$SSHD_CONFIG"
  else
    echo "${key} ${val}" >> "$SSHD_CONFIG"
  fi
done

sshd -t && systemctl reload sshd
log "SSH hardened. Ensure your SSH key is authorised before logging out."

# ── 5. UFW firewall ───────────────────────────────────────────────────────────
log "Configuring UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
# Allow Docker internal networks to reach each other
ufw --force enable
ufw status verbose

# ── 6. fail2ban ───────────────────────────────────────────────────────────────
log "Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5
backend  = systemd

[sshd]
enabled  = true
port     = ssh
logpath  = %(sshd_log)s

[nginx-http-auth]
enabled  = true

[nginx-botsearch]
enabled  = true
EOF

systemctl enable --now fail2ban
systemctl restart fail2ban
log "fail2ban configured."

# ── 7. Time synchronisation ───────────────────────────────────────────────────
log "Enabling chrony (NTP)..."
systemctl enable --now chrony
chronyc tracking | head -5

# ── 8. Kernel tuning ──────────────────────────────────────────────────────────
log "Applying kernel tuning parameters..."
cat > /etc/sysctl.d/99-n8n-production.conf << 'EOF'
# Increase TCP backlog
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535

# Reuse TIME_WAIT sockets
net.ipv4.tcp_tw_reuse = 1

# Increase file descriptor limits
fs.file-max = 1048576

# Virtual memory (Redis AOF performance)
vm.overcommit_memory = 1

# Disable transparent huge pages (Redis recommendation)
# Note: also disable THP in rc.local / systemd unit for full effect
kernel.numa_balancing = 0
EOF
sysctl --system

# Disable THP at runtime
if [[ -f /sys/kernel/mm/transparent_hugepage/enabled ]]; then
  echo never > /sys/kernel/mm/transparent_hugepage/enabled
  echo never > /sys/kernel/mm/transparent_hugepage/defrag
fi

# Persist THP disable across reboots using a systemd one-shot service
# (rc.local is deprecated in systemd-based Ubuntu 22.04+)
cat > /etc/systemd/system/disable-thp.service << 'EOF'
[Unit]
Description=Disable Transparent Huge Pages (THP)
DefaultDependencies=no
After=sysinit.target local-fs.target
Before=basic.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/enabled'
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/defrag'
RemainAfterExit=yes

[Install]
WantedBy=basic.target
EOF

systemctl daemon-reload
systemctl enable --now disable-thp

# ── 9. Docker Engine ──────────────────────────────────────────────────────────
log "Installing Docker Engine..."
if command -v docker &>/dev/null; then
  warn "Docker already installed: $(docker --version). Skipping."
else
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  systemctl enable --now docker
  log "Docker installed: $(docker --version)"
  log "Docker Compose: $(docker compose version)"
fi

# Add deploy user to docker group
if [[ -n "$DEPLOY_USER" ]]; then
  usermod -aG docker "$DEPLOY_USER"
  log "Added $DEPLOY_USER to the docker group."
fi

# ── 10. Unattended security upgrades ─────────────────────────────────────────
log "Enabling automatic security upgrades..."
apt-get install -y unattended-upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades

# ── Done ──────────────────────────────────────────────────────────────────────
log ""
log "════════════════════════════════════════════════════════"
log " VPS baseline setup complete!"
log ""
log " Next steps:"
log "   1. Add your SSH public key to ~/.ssh/authorized_keys"
log "   2. Verify SSH login as $DEPLOY_USER (keep root session open!)"
log "   3. Point DNS A/AAAA records to this server's IP"
log "   4. Obtain a TLS certificate (see docs/runbook.md)"
log "   5. Clone this repo and run: cp .env.example .env"
log "   6. Edit .env, then: docker compose up -d"
log "════════════════════════════════════════════════════════"
