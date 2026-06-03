#!/bin/bash
# =============================================================================
# DefenseFood — Secure Production Deployment Script
# Domain: configure DOMAIN below (or pass via env)
# =============================================================================
#
# Deploys the DefenseFood full stack on a fresh Ubuntu 24.04 EC2 instance:
#   • Rust PyO3 engine (defensefood_core, built via maturin into the venv)
#   • Python FastAPI backend (uvicorn, 2 workers)
#   • Next.js frontend (food-defence)
#   • Nginx reverse proxy + Let's Encrypt SSL
#   • UFW + fail2ban + automatic security updates
#
# Usage:
#   ALLOWED_SSH_IP=70.82.222.52 DOMAIN=defensefood.example.com \
#     ./deploy/deploy-defensefood.sh
#
# Flags:
#   --skip-security   Skip Phase 1 (firewall/fail2ban/SSH hardening)
#   --skip-ssl        Skip Phase 5.2 (certbot)
#   --skip-data-check Skip the data-prerequisite verification in Phase 3
#
# Prereqs on the EC2 instance:
#   • Ubuntu 24.04 LTS, ubuntu user with sudo
#   • Security group: 22 (from your IP), 80, 443
#   • DNS A record for DOMAIN → instance public IP (only needed for SSL)
#
# Data prerequisites (uploaded by hand BEFORE running this script —
# see DEPLOYMENT.md for scp/rsync recipes):
#   • backend/updated_data_rasff_window.xlsx       (already in git)
#   • backend/data/faostat/*.csv                   (upload separately)
#   • backend/script/output/merged_trade_data.csv  (upload separately)
# =============================================================================

set -euo pipefail

# =============================================================================
# CONFIGURATION — edit these or override via environment variables
# =============================================================================

ALLOWED_SSH_IP="${ALLOWED_SSH_IP:-YOUR_IP_HERE}"

PROJECT_DIR="${PROJECT_DIR:-/var/www/defensefood}"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/food-defence"
RUST_CRATE_DIR="$PROJECT_DIR/crates/defensefood_core"
VENV_DIR="$BACKEND_DIR/venv"

DOMAIN="${DOMAIN:-defensefood.example.com}"
SSL_EMAIL="${SSL_EMAIL:-dishdevinfo@gmail.com}"

GIT_REPO="${GIT_REPO:-git@github.com:YOUR_ORG/defensefood.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"

# Memory watchdog threshold (MB). Defensefood loads big DataFrames at boot;
# on a t3.large with ~8GB RAM, restart uvicorn workers if available memory
# falls below this.
MEMORY_THRESHOLD_MB="${MEMORY_THRESHOLD_MB:-1500}"

# Uvicorn workers. Each worker independently loads the full state (corridor
# metrics + pandas DataFrames + FAOSTAT lookups + scoring) at startup. That
# work is CPU-heavy pandas, and t3.large only has 2 vCPUs, so two parallel
# workers will saturate the box and starve each other on cold boot, often
# without ever reaching "Application startup complete". One worker is the
# safe default; bump only on instances with >= 4 vCPUs and confirmed
# memory headroom (each worker is ~800MB to 1.2GB resident).
API_WORKERS="${API_WORKERS:-1}"

# =============================================================================
# COLORS AND HELPERS
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║         DefenseFood — Secure Production Deployment               ║"
    echo "║         RASFF / Comtrade / FAOSTAT food-fraud intelligence       ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_status() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }
print_step() { echo -e "\n${BLUE}[STEP]${NC} $1\n"; }
print_section() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# Idempotent cron-line installer that tolerates a missing crontab.
#
# On a fresh user (or freshly-baked AMI) `crontab -l` exits 1 because there is
# no crontab at all, and with `set -euo pipefail` that kills the script.
# We swallow that exit code and re-write the crontab so the line is present
# exactly once regardless of prior state.
#
# Usage:
#   install_cron        "grep-key"  "cron-line"   # current user
#   install_cron --sudo "grep-key"  "cron-line"   # root crontab
install_cron() {
    local cron_cmd="crontab"
    if [ "${1:-}" = "--sudo" ]; then
        cron_cmd="sudo crontab"
        shift
    fi
    local key="$1"
    local line="$2"
    {
        $cron_cmd -l 2>/dev/null | grep -v -F "$key" || true
        echo "$line"
    } | $cron_cmd -
}

SKIP_SECURITY=false
SKIP_SSL=false
SKIP_DATA_CHECK=false
for arg in "$@"; do
    case $arg in
        --skip-security)   SKIP_SECURITY=true ;;
        --skip-ssl)        SKIP_SSL=true ;;
        --skip-data-check) SKIP_DATA_CHECK=true ;;
    esac
done

# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================

print_banner

if [[ $EUID -eq 0 ]]; then
    print_error "Do not run as root. Run as ubuntu user with sudo access."
    exit 1
fi

if [[ "$ALLOWED_SSH_IP" == "YOUR_IP_HERE" ]]; then
    print_error "ALLOWED_SSH_IP is not set."
    print_warning "Find your IP: curl -s ifconfig.me"
    print_warning "Then run: ALLOWED_SSH_IP=your.ip.here ./deploy/deploy-defensefood.sh"
    exit 1
fi

if [[ "$DOMAIN" == "defensefood.example.com" && "$SKIP_SSL" == false ]]; then
    print_warning "DOMAIN is still the placeholder. SSL will request a cert for that."
    print_warning "Either set DOMAIN=your.domain or run with --skip-ssl."
fi

print_status "SSH access will be restricted to: $ALLOWED_SSH_IP"
print_status "Target domain: $DOMAIN"
print_warning "Make sure $ALLOWED_SSH_IP is YOUR IP or you will be locked out!"
echo ""
read -rp "Press Enter to continue or Ctrl+C to abort..."

# =============================================================================
# PHASE 1: SECURITY HARDENING
# =============================================================================

if [[ "$SKIP_SECURITY" == false ]]; then
    print_section "PHASE 1: SECURITY HARDENING"

    print_step "1.1 System updates"
    sudo apt update
    sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y
    print_status "System updated"

    print_step "1.2 Installing security tools"
    sudo apt install -y \
        fail2ban \
        ufw \
        unattended-upgrades \
        apt-listchanges \
        logwatch \
        rkhunter
    print_status "Security tools installed"

    print_step "1.3 Configuring firewall (UFW)"
    sudo ufw --force reset
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow from "$ALLOWED_SSH_IP" to any port 22 proto tcp comment 'SSH from allowed IP'
    sudo ufw allow 80/tcp  comment 'HTTP'
    sudo ufw allow 443/tcp comment 'HTTPS'
    # Block common mining-pool ports (defensive hygiene)
    sudo ufw deny out to any port 10128 comment 'Block mining pool port'
    sudo ufw deny out to any port 3333  comment 'Block mining pool port'
    sudo ufw --force enable
    sudo ufw status verbose
    print_status "Firewall configured"

    print_step "1.4 Configuring fail2ban"
    sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
bantime = 86400
findtime = 600
maxretry = 5
backend = systemd
banaction = ufw

[sshd]
enabled = true
port = ssh
filter = sshd
maxretry = 3
bantime = 86400
findtime = 600
EOF
    sudo systemctl enable fail2ban
    sudo systemctl restart fail2ban
    print_status "fail2ban configured"

    print_step "1.5 Configuring automatic security updates"
    sudo tee /etc/apt/apt.conf.d/20auto-upgrades > /dev/null << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
EOF
    sudo tee /etc/apt/apt.conf.d/50unattended-upgrades > /dev/null << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF
    sudo systemctl enable unattended-upgrades
    sudo systemctl start unattended-upgrades
    print_status "Auto-updates configured"

    print_step "1.6 SSH hardening"
    sudo tee /etc/ssh/sshd_config.d/hardening.conf > /dev/null << 'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
PermitEmptyPasswords no
ChallengeResponseAuthentication no
UsePAM yes
EOF
    if sudo sshd -t; then
        sudo systemctl restart sshd || sudo systemctl restart ssh
        print_status "SSH hardened"
    else
        print_error "SSH config invalid — leaving previous config in place"
    fi

    print_step "1.7 Installing security check script"
    sudo tee /usr/local/bin/security-check.sh > /dev/null << 'EOFSCRIPT'
#!/bin/bash
echo "=== Security Check $(date) ==="
echo -e "\n--- Crontabs ---"
for user in $(cut -f1 -d: /etc/passwd); do
    crontab -u $user -l 2>/dev/null | grep -v "^#" | grep -v "^$" && echo "  ^ User: $user"
done
echo -e "\n--- Suspicious processes ---"
ps aux | grep -E "(xmrig|kdevtmpfsi|pnscan|/dev/shm/|/var/tmp/\.)" | grep -v grep || echo "None found"
echo -e "\n--- High CPU processes ---"
ps aux --sort=-%cpu | head -5
echo -e "\n--- Failed SSH attempts (last 24h) ---"
sudo grep "Failed password\|Invalid user" /var/log/auth.log 2>/dev/null | tail -10 || echo "None"
echo -e "\n--- fail2ban status ---"
sudo fail2ban-client status sshd 2>/dev/null || echo "fail2ban not running"
echo -e "\n--- Listening ports ---"
sudo ss -tlnp
echo -e "\n--- SSH authorized_keys ---"
cat ~/.ssh/authorized_keys 2>/dev/null | cut -d' ' -f3
echo -e "\n=== Check Complete ==="
EOFSCRIPT
    sudo chmod +x /usr/local/bin/security-check.sh
    install_cron "security-check.sh" \
        "0 8 * * 1 /usr/local/bin/security-check.sh >> /var/log/security-check.log 2>&1"
    print_status "Security monitoring scheduled (Mondays 08:00)"

    print_step "1.8 Temp directory cleanup"
    sudo tee /etc/tmpfiles.d/tmp-clean.conf > /dev/null << 'EOF'
D /tmp 1777 root root 1d
D /var/tmp 1777 root root 7d
D /dev/shm 1777 root root 1d
EOF
    print_status "tmpfiles.d entries written"

    print_status "Phase 1 complete"
else
    print_warning "Skipping security hardening (--skip-security)"
fi

# =============================================================================
# PHASE 2: SYSTEM DEPENDENCIES
# =============================================================================

print_section "PHASE 2: SYSTEM DEPENDENCIES"

print_step "2.1 Build dependencies"
sudo apt install -y \
    python3 python3-pip python3-venv python3-dev \
    nginx supervisor certbot python3-certbot-nginx \
    curl wget git build-essential \
    pkg-config libssl-dev \
    jq htop unzip
print_status "Apt packages installed"

print_step "2.2 Rust toolchain"
if ! command -v cargo &> /dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi
# shellcheck disable=SC1091
source "$HOME/.cargo/env"
rustc --version
cargo --version
print_status "Rust ready"

print_step "2.3 Node.js 20.x"
if ! command -v node &> /dev/null || ! node --version | grep -q "v20"; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
fi
print_status "Node.js $(node --version)"

print_step "2.4 Python version check (PyO3 compatibility)"
# PyO3 0.23 supports up to Python 3.13. Ubuntu 26.04+ ships 3.14 by default,
# which PyO3 rejects at build time. If the system Python is too new, install
# Python 3.13 via uv (a portable, no-PPA, no-root option) and reuse it for
# the backend venv in Phase 3.
PYTHON_BIN="python3"
SYS_PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "0")
if [ "$SYS_PY_MINOR" -gt 13 ]; then
    print_warning "System Python is 3.${SYS_PY_MINOR}; PyO3 0.23 caps at 3.13"
    print_warning "Installing Python 3.13 via uv (user-space, no PPA needed)"
    if ! command -v uv &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # shellcheck disable=SC1091
        source "$HOME/.local/bin/env"
    fi
    uv python install 3.13
    PYTHON_BIN="$(uv python find 3.13)"
    print_status "Using $PYTHON_BIN for the backend venv"
else
    print_status "System Python 3.${SYS_PY_MINOR} is within PyO3 0.23's supported range"
fi
export PYTHON_BIN

# =============================================================================
# PHASE 3: APPLICATION DEPLOYMENT
# =============================================================================

print_section "PHASE 3: APPLICATION DEPLOYMENT"

print_step "3.1 Cloning repository"
if [ -d "$PROJECT_DIR/.git" ]; then
    print_warning "Project exists — pulling latest"
    cd "$PROJECT_DIR"
    git fetch --all
    git checkout "$GIT_BRANCH"
    git pull origin "$GIT_BRANCH"
else
    sudo mkdir -p "$(dirname "$PROJECT_DIR")"
    sudo chown "$USER:$USER" "$(dirname "$PROJECT_DIR")"
    git clone -b "$GIT_BRANCH" "$GIT_REPO" "$PROJECT_DIR"
fi
sudo chown -R "$USER:$USER" "$PROJECT_DIR"
print_status "Repo at $PROJECT_DIR"

print_step "3.2 Verifying data prerequisites"
if [[ "$SKIP_DATA_CHECK" == false ]]; then
    missing=0
    [ -f "$BACKEND_DIR/updated_data_rasff_window.xlsx" ] \
        && print_status "RASFF Excel present" \
        || { print_error "MISSING: $BACKEND_DIR/updated_data_rasff_window.xlsx"; missing=1; }

    if [ -d "$BACKEND_DIR/data/faostat" ] && \
       compgen -G "$BACKEND_DIR/data/faostat/*.csv" > /dev/null; then
        print_status "FAOSTAT CSVs present ($(ls "$BACKEND_DIR/data/faostat/"*.csv | wc -l) files)"
    else
        print_error "MISSING: $BACKEND_DIR/data/faostat/ (no CSVs found)"
        print_warning "Section 2/3 metrics will run in trade-only fallback mode"
        missing=1
    fi

    if [ -f "$BACKEND_DIR/script/output/merged_trade_data.csv" ]; then
        sz=$(du -h "$BACKEND_DIR/script/output/merged_trade_data.csv" | cut -f1)
        print_status "Merged trade CSV present ($sz)"
    else
        print_error "MISSING: $BACKEND_DIR/script/output/merged_trade_data.csv"
        print_warning "Sections 5 / 6.4 / 7 will have very limited coverage"
        missing=1
    fi

    if [ $missing -ne 0 ]; then
        print_warning "Data files are missing. Upload them now (see DEPLOYMENT.md)"
        print_warning "or re-run with --skip-data-check to proceed regardless."
        read -rp "Press Enter to continue anyway, or Ctrl+C to abort and upload data..."
    fi
else
    print_warning "Skipping data-prerequisite check (--skip-data-check)"
fi

print_step "3.3 Setting up Python virtual environment"
cd "$BACKEND_DIR"
# Use the resolved interpreter from Phase 2.4 (system python3 by default, or
# uv-managed 3.13 when the system is too new for PyO3).
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ ! -d "$VENV_DIR" ]; then
    if command -v uv &> /dev/null && [[ "$PYTHON_BIN" != "python3" ]]; then
        # --seed installs pip + setuptools + wheel into the venv. Without it,
        # `pip install` later falls through to the system Python 3.14 pip,
        # which on Ubuntu 26.04 refuses with PEP 668 externally-managed.
        uv venv --seed --python "$PYTHON_BIN" "$VENV_DIR"
    else
        "$PYTHON_BIN" -m venv "$VENV_DIR"
    fi
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip wheel
print_status "venv ready at $VENV_DIR (python $(python --version 2>&1 | awk '{print $2}'))"

print_step "3.4 Building Rust extension via maturin"
# maturin develop installs the compiled cdylib into the active venv as
# `defensefood_core` (declared in backend/pyproject.toml as defensefood-core).
pip install maturin
cd "$RUST_CRATE_DIR"
# shellcheck disable=SC1091
source "$HOME/.cargo/env"
VIRTUAL_ENV="$VENV_DIR" PATH="$VENV_DIR/bin:$PATH" \
    python -m maturin develop --release
python -c "import defensefood_core; print('defensefood_core:', defensefood_core.__file__)"
print_status "Rust extension installed into venv"

print_step "3.5 Installing Python dependencies"
cd "$BACKEND_DIR"
if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    pip install -r "$BACKEND_DIR/requirements.txt"
elif [ -f "$BACKEND_DIR/pyproject.toml" ]; then
    pip install -e .
elif [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip install -r "$PROJECT_DIR/requirements.txt"
fi
python -c "import fastapi, uvicorn, pandas, defensefood_core; print('Backend imports OK')"
print_status "Backend dependencies installed"

print_step "3.6 Backend .env"
cat > "$BACKEND_DIR/.env" << EOF
# DefenseFood backend environment — production
DEFENSEFOOD_CORS_ORIGINS=https://${DOMAIN},https://www.${DOMAIN}
DEFENSEFOOD_FAOSTAT_DIR=${BACKEND_DIR}/data/faostat

# CORS: by default localhost:3000 / 3001 / 5000 are ALSO allowed so a
# developer's local Next.js can hit this production API for debugging.
# Browsers set the Origin header from the page URL (it cannot be forged
# by a remote site), so allowing localhost in production is safe. To lock
# the API down to the env-configured origins only, set this to "false":
# DEFENSEFOOD_CORS_ALLOW_LOCALHOST=false

# Optional — only needed if running the Comtrade fetcher on this server
# (the API itself does not need these to serve cached data):
# COMTRADE_SUBSCRIPTION_KEYS=key1,key2
# COMTRADE_SUBSCRIPTION_KEY=legacy_single_key

PYTHONUNBUFFERED=1
EOF
chmod 600 "$BACKEND_DIR/.env"
print_status "Backend .env written"

print_step "3.7 Building Next.js frontend"
cd "$FRONTEND_DIR"
rm -rf .next node_modules/.cache 2>/dev/null || true
cat > "$FRONTEND_DIR/.env.production.local" << EOF
NEXT_PUBLIC_API_URL=https://${DOMAIN}/api/v1
EOF
chmod 600 "$FRONTEND_DIR/.env.production.local"

# Build (allow more memory for large dependency graph)
NODE_OPTIONS="--max-old-space-size=2048" npm ci
NODE_OPTIONS="--max-old-space-size=2048" npm run build
print_status "Frontend built"

# =============================================================================
# PHASE 4: SERVER CONFIGURATION
# =============================================================================

print_section "PHASE 4: SERVER CONFIGURATION"

print_step "4.1 Nginx config"
sudo tee /etc/nginx/sites-available/defensefood > /dev/null << EOF
# Rate-limit zones
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone \$binary_remote_addr zone=general_limit:10m rate=30r/s;
limit_conn_zone \$binary_remote_addr zone=conn_limit:10m;

upstream defensefood_api {
    server 127.0.0.1:8000 fail_timeout=30s;
    keepalive 32;
}

upstream defensefood_frontend {
    server 127.0.0.1:3000 fail_timeout=30s;
    keepalive 32;
}

# Block direct IP access — close anything not matching the server_name below
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 444;
}

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # Security headers
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 20M;

    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_redirect off;
    proxy_read_timeout 300;
    proxy_connect_timeout 300;
    proxy_send_timeout 300;

    # API — backend serves under /api/v1 directly; pass-through with no rewrite.
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        limit_conn conn_limit 10;
        proxy_pass http://defensefood_api;
    }

    # Next.js static assets — long-cache
    location /_next/static/ {
        proxy_pass http://defensefood_frontend;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # Frontend (everything else)
    location / {
        limit_req zone=general_limit burst=50 nodelay;
        proxy_pass http://defensefood_frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_cache_bypass \$http_upgrade;
    }

    error_page 502 503 504 /50x.html;
    location = /50x.html {
        root /var/www/html;
        internal;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/defensefood /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
print_status "Nginx configured"

sudo mkdir -p /var/www/html
sudo tee /var/www/html/50x.html > /dev/null << 'EOF'
<!DOCTYPE html>
<html><head><title>DefenseFood — temporarily unavailable</title>
<style>body{font-family:-apple-system,sans-serif;text-align:center;margin-top:100px;background:linear-gradient(135deg,#1e293b,#334155);color:white;padding:20px}
.box{background:rgba(255,255,255,.08);border-radius:20px;padding:40px;max-width:600px;margin:0 auto}</style></head>
<body><div class="box"><h1>DefenseFood</h1><h2>Service temporarily unavailable</h2>
<p>The intelligence service is restarting. Please try again in a moment.</p></div></body></html>
EOF

print_step "4.2 Supervisor — API + frontend"

NPM_PATH=$(which npm)

sudo tee /etc/supervisor/conf.d/defensefood-api.conf > /dev/null << EOF
[program:defensefood-api]
command=$VENV_DIR/bin/uvicorn defensefood.api.main:app --host 127.0.0.1 --port 8000 --workers $API_WORKERS --env-file .env
directory=$BACKEND_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/defensefood-api.log
stderr_logfile=/var/log/defensefood-api-error.log
environment=PATH="$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin",PYTHONPATH="$BACKEND_DIR",PYTHONUNBUFFERED="1"
stopwaitsecs=120
stopsignal=KILL
stopasgroup=true
killasgroup=true
EOF

sudo tee /etc/supervisor/conf.d/defensefood-frontend.conf > /dev/null << EOF
[program:defensefood-frontend]
command=$NPM_PATH start
directory=$FRONTEND_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/defensefood-frontend.log
stderr_logfile=/var/log/defensefood-frontend-error.log
environment=NODE_ENV="production",PORT="3000",NODE_OPTIONS="--max-old-space-size=1024"
stopwaitsecs=60
stopsignal=KILL
stopasgroup=true
killasgroup=true
EOF

sudo touch /var/log/defensefood-{api,api-error,frontend,frontend-error}.log
sudo chown "$USER:$USER" /var/log/defensefood-*.log
print_status "Supervisor programs registered"

print_step "4.3 Memory watchdog"
# Restart the API workers if available memory dips below the threshold.
# Defensefood loads ~500-800MB per uvicorn worker at startup (corridors +
# pandas DataFrames + FAOSTAT lookups); this catches slow leaks before OOM.
sudo tee /usr/local/bin/defensefood-memory-watchdog.sh > /dev/null << EOFWD
#!/bin/bash
# Memory watchdog — restart API workers if MemAvailable falls below threshold.
# Runs from cron every 5 minutes.

THRESHOLD_MB=$MEMORY_THRESHOLD_MB
LOG=/var/log/defensefood/memory-watchdog.log

mkdir -p /var/log/defensefood

available_kb=\$(grep MemAvailable /proc/meminfo | awk '{print \$2}')
available_mb=\$((available_kb / 1024))
total_kb=\$(grep MemTotal /proc/meminfo | awk '{print \$2}')
total_mb=\$((total_kb / 1024))
used_mb=\$((total_mb - available_mb))
pct=\$((used_mb * 100 / total_mb))

if [ "\$available_mb" -lt "\$THRESHOLD_MB" ]; then
    echo "\$(date '+%Y-%m-%d %H:%M:%S') WARN available=\${available_mb}MB (<\${THRESHOLD_MB}MB) — restarting defensefood-api" >> "\$LOG"
    sudo supervisorctl restart defensefood-api
    echo "\$(date '+%Y-%m-%d %H:%M:%S') INFO defensefood-api restarted" >> "\$LOG"
else
    # Hourly baseline (every 12th run — adjust as needed)
    minute=\$(date +%M)
    if [ "\$((10#\$minute % 60))" -lt 5 ]; then
        echo "\$(date '+%Y-%m-%d %H:%M:%S') OK available=\${available_mb}MB used=\${used_mb}MB (\${pct}%)" >> "\$LOG"
    fi
fi
EOFWD
sudo chmod +x /usr/local/bin/defensefood-memory-watchdog.sh
sudo mkdir -p /var/log/defensefood
sudo chown "$USER:$USER" /var/log/defensefood
# Install root cron (sudo restart needs root)
install_cron --sudo "defensefood-memory-watchdog" \
    "*/5 * * * * /usr/local/bin/defensefood-memory-watchdog.sh"
print_status "Memory watchdog scheduled (threshold ${MEMORY_THRESHOLD_MB}MB, every 5 min)"

# =============================================================================
# PHASE 5: SSL AND STARTUP
# =============================================================================

print_section "PHASE 5: SSL AND STARTUP"

print_step "5.1 Starting services"
sudo systemctl enable nginx supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo systemctl start nginx
sudo supervisorctl start all
print_status "Waiting 15s for services to settle (FastAPI cold-load is slow)..."
sleep 15
sudo supervisorctl status

print_step "5.2 SSL certificate"
if [[ "$SKIP_SSL" == false ]]; then
    sudo mkdir -p /etc/letsencrypt
    if [ ! -f "/etc/letsencrypt/options-ssl-nginx.conf" ]; then
        sudo curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf -o /etc/letsencrypt/options-ssl-nginx.conf
        sudo curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem -o /etc/letsencrypt/ssl-dhparams.pem
    fi

    # Always request the apex. Only add `www.<DOMAIN>` if a record actually
    # exists — otherwise Let's Encrypt fails the whole transaction with
    # NXDOMAIN on the missing record (one bad SAN sinks the cert).
    cert_args=(-d "$DOMAIN")
    if getent hosts "www.$DOMAIN" > /dev/null 2>&1; then
        cert_args+=(-d "www.$DOMAIN")
        print_status "Including www.$DOMAIN in the cert request"
    else
        print_warning "www.$DOMAIN has no DNS record; requesting cert for $DOMAIN only"
    fi

    print_warning "Requesting certificate. DNS must already point $DOMAIN → $(curl -s ifconfig.me)"
    if sudo certbot --nginx "${cert_args[@]}" \
        --non-interactive --agree-tos --email "$SSL_EMAIL" --redirect; then
        print_status "SSL certificate installed"
        sudo nginx -t && sudo systemctl reload nginx
    else
        print_error "Certbot failed — fix DNS / firewall and re-run: sudo certbot --nginx ${cert_args[*]}"
    fi
    install_cron --sudo "certbot renew" \
        "0 12 * * * /usr/bin/certbot renew --quiet && systemctl reload nginx"
else
    print_warning "Skipping SSL (--skip-ssl)"
fi

# =============================================================================
# PHASE 6: HEALTH CHECKS + UTILITY SCRIPTS
# =============================================================================

print_section "PHASE 6: HEALTH CHECKS + UTILITIES"

print_step "6.1 Local health checks"
if curl -sf http://localhost:8000/api/v1/research/coverage > /dev/null 2>&1; then
    print_status "API responding"
else
    print_warning "API not responding — tail /var/log/defensefood-api.log"
fi
if curl -sf http://localhost:3000 > /dev/null 2>&1; then
    print_status "Frontend responding"
else
    print_warning "Frontend not responding — tail /var/log/defensefood-frontend.log"
fi

print_step "6.2 Installing utility scripts"

# Update — pull + rebuild + restart
sudo tee /usr/local/bin/defensefood-update.sh > /dev/null << EOFUPDATE
#!/bin/bash
set -e
echo "Updating DefenseFood…"
cd $PROJECT_DIR
git pull origin $GIT_BRANCH

cd $RUST_CRATE_DIR
source \$HOME/.cargo/env
VIRTUAL_ENV=$VENV_DIR PATH=$VENV_DIR/bin:\$PATH \
    python -m maturin develop --release

cd $BACKEND_DIR
source $VENV_DIR/bin/activate
[ -f requirements.txt ] && pip install -r requirements.txt || true
[ -f pyproject.toml ]  && pip install -e .              || true

cd $FRONTEND_DIR
NODE_OPTIONS="--max-old-space-size=2048" npm ci
NODE_OPTIONS="--max-old-space-size=2048" npm run build

sudo supervisorctl restart all
sudo systemctl reload nginx
echo "Update complete."
EOFUPDATE
sudo chmod +x /usr/local/bin/defensefood-update.sh

# Status
sudo tee /usr/local/bin/defensefood-status.sh > /dev/null << 'EOFSTATUS'
#!/bin/bash
echo "=== DefenseFood Status ==="
echo ""
echo "Services:"
sudo supervisorctl status
echo ""
echo "Firewall:"
sudo ufw status | head -20
echo ""
echo "fail2ban:"
sudo fail2ban-client status sshd 2>/dev/null | grep -E "(Currently|Total)" || echo "Not running"
echo ""
echo "Disk:"
df -h / | tail -1
echo ""
echo "Memory:"
free -h | grep -E "(Mem|Swap)"
echo ""
echo "Top processes:"
ps aux --sort=-%mem | head -6
EOFSTATUS
sudo chmod +x /usr/local/bin/defensefood-status.sh

# Daily backup of code + .env (skips node_modules / target / venv / .next)
sudo tee /usr/local/bin/defensefood-backup.sh > /dev/null << EOFBK
#!/bin/bash
DIR=/var/backups/defensefood
DATE=\$(date +%Y%m%d_%H%M%S)
mkdir -p \$DIR
tar --exclude='node_modules' --exclude='venv' --exclude='target' \\
    --exclude='.next' --exclude='backend/data/faostat' \\
    --exclude='backend/script/output/merged_trade_data.csv' \\
    -czf \$DIR/defensefood_\$DATE.tar.gz $PROJECT_DIR
find \$DIR -name "defensefood_*.tar.gz" -mtime +7 -delete
echo "Backup: \$DIR/defensefood_\$DATE.tar.gz"
EOFBK
sudo chmod +x /usr/local/bin/defensefood-backup.sh
install_cron --sudo "defensefood-backup" \
    "0 2 * * * /usr/local/bin/defensefood-backup.sh >> /var/log/defensefood/backup.log 2>&1"

print_status "Utility scripts installed"

# =============================================================================
# COMPLETION
# =============================================================================

print_banner
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                  DEPLOYMENT COMPLETE                             ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

cat << EOF

Application URLs:
   • https://$DOMAIN
   • http://$(curl -s ifconfig.me)/

Paths:
   • Project:         $PROJECT_DIR
   • Backend venv:    $VENV_DIR
   • API logs:        /var/log/defensefood-api.log
   • Frontend logs:   /var/log/defensefood-frontend.log
   • Watchdog log:    /var/log/defensefood/memory-watchdog.log
   • Backups:         /var/backups/defensefood/

Utility commands:
   • Status:    defensefood-status.sh
   • Update:    sudo /usr/local/bin/defensefood-update.sh
   • Backup:    sudo /usr/local/bin/defensefood-backup.sh
   • Security:  sudo /usr/local/bin/security-check.sh
   • Restart:   sudo supervisorctl restart all

Next steps:
   1. Verify SSL  : curl -sI https://$DOMAIN | head
   2. Coverage    : curl https://$DOMAIN/api/v1/research/coverage | jq
   3. If data files were missing, upload them and run:
        sudo supervisorctl restart defensefood-api
   4. Add COMTRADE_SUBSCRIPTION_KEYS to $BACKEND_DIR/.env only if you plan
      to re-fetch trade data on this server; otherwise leave it out.

EOF
