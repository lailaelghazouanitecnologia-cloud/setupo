#!/bin/bash
# NSO Agent — One-line installer
# Usage: curl -fsSL https://nso.dev/install | bash
#   or:  curl -fsSL https://nso.dev/install | bash -s -- --host https://nso.dev --token sk_live_xxx
#
# This installs the NSO agent on your server, connects it to the NSO platform,
# and sets up nginx + SSL. Requires root or sudo.

set -euo pipefail

# ── Config ──
NSO_VERSION="0.3.0"
NSO_DIR="/opt/nso"
NSO_USER="nso"
NSO_AGENT_PORT=8081
NSO_HOST="${NSO_HOST:-https://nso.dev}"
NSO_TOKEN="${NSO_TOKEN:-}"
NSO_DOMAIN="${NSO_DOMAIN:-}"
NSO_ADMIN_EMAIL="${NSO_ADMIN_EMAIL:-}"
NSO_ADMIN_PASSWORD="${NSO_ADMIN_PASSWORD:-}"
NSO_CENTRAL="${NSO_CENTRAL:-false}"  # Set to true to install as central server with PostgreSQL
DB_PASSWORD="${DB_PASSWORD:-}"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[nso]${NC} $*"; }
ok()    { echo -e "${GREEN}[nso]${NC} $*"; }
warn()  { echo -e "${YELLOW}[nso]${NC} $*"; }
error() { echo -e "${RED}[nso]${NC} $*" >&2; }
die()   { error "$*"; exit 1; }

# ── Parse args ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)     NSO_HOST="$2"; shift 2 ;;
        --token)    NSO_TOKEN="$2"; shift 2 ;;
        --domain)   NSO_DOMAIN="$2"; shift 2 ;;
        --email)    NSO_ADMIN_EMAIL="$2"; shift 2 ;;
        --password) NSO_ADMIN_PASSWORD="$2"; shift 2 ;;
        --central)  NSO_CENTRAL="true"; shift ;;
        --db-password) DB_PASSWORD="$2"; shift 2 ;;
        --help)
            echo "Usage: curl -fsSL https://nso.dev/install | bash -s -- [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --host URL       NSO platform URL (default: https://nso.dev)"
            echo "  --token TOKEN    API key (sk_live_...) to link this instance"
            echo "  --domain DOMAIN  Domain for this server (auto-detected if not set)"
            echo "  --email EMAIL    Admin email for certbot"
            echo "  --password PASS  Agent admin password (auto-generated if not set)"
            echo ""
            echo "Environment variables: NSO_HOST, NSO_TOKEN, NSO_DOMAIN, NSO_ADMIN_EMAIL, NSO_ADMIN_PASSWORD"
            exit 0
            ;;
        *) die "Unknown option: $1" ;;
    esac
done

# ── Preflight ──
[[ $EUID -eq 0 ]] || die "This installer must be run as root (use sudo)"

info "NSO Agent Installer v${NSO_VERSION}"
info "Platform: ${NSO_HOST}"
echo ""

# Detect OS
if ! command -v apt-get &>/dev/null; then
    die "Only Debian/Ubuntu is supported (apt-get not found)"
fi

# Detect IP
SERVER_IP=$(curl -4 -fsSL --max-time 5 https://ifconfig.me 2>/dev/null || \
            curl -4 -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || \
            hostname -I | awk '{print $1}')
info "Server IP: ${SERVER_IP}"

# Auto-detect domain via reverse DNS
if [[ -z "$NSO_DOMAIN" ]]; then
    NSO_DOMAIN=$(dig +short -x "$SERVER_IP" 2>/dev/null | sed 's/\.$//' || true)
    if [[ -z "$NSO_DOMAIN" || "$NSO_DOMAIN" == *"vultr"* || "$NSO_DOMAIN" == *"compute"* ]]; then
        NSO_DOMAIN=""
    fi
fi

# Generate password if not set
if [[ -z "$NSO_ADMIN_PASSWORD" ]]; then
    NSO_ADMIN_PASSWORD=$(openssl rand -hex 32)
fi

# Generate JWT secret
NSO_JWT_SECRET=$(openssl rand -hex 32)

# ── Step 1: System packages ──
info "Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx python3-pip python3-venv \
    git curl ufw jq unzip fail2ban > /dev/null 2>&1
ok "System packages installed"

# ── Step 1b: PostgreSQL (central server only) ──
if [[ "$NSO_CENTRAL" == "true" ]]; then
    info "Installing PostgreSQL (central server mode)..."
    apt-get install -y -qq postgresql postgresql-contrib > /dev/null 2>&1
    systemctl enable postgresql
    systemctl start postgresql

    [[ -z "$DB_PASSWORD" ]] && DB_PASSWORD=$(openssl rand -hex 24)
    DATABASE_URL="postgresql://nso:${DB_PASSWORD}@localhost:5432/nso"

    # Create user and database
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='nso'" | grep -q 1 \
        || sudo -u postgres psql -c "CREATE USER nso WITH PASSWORD '${DB_PASSWORD}';" > /dev/null
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='nso'" | grep -q 1 \
        || sudo -u postgres psql -c "CREATE DATABASE nso OWNER nso;" > /dev/null
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE nso TO nso;" > /dev/null
    sudo -u postgres psql -d nso -c "GRANT ALL ON SCHEMA public TO nso;" > /dev/null
    ok "PostgreSQL ready (user: nso, db: nso)"
fi

# ── Step 2: Node.js 20 ──
if ! command -v node &>/dev/null || [[ $(node -v 2>/dev/null | cut -d. -f1 | tr -d v) -lt 18 ]]; then
    info "Installing Node.js 20 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null 2>&1
    apt-get install -y -qq nodejs > /dev/null 2>&1
    ok "Node.js $(node -v) installed"
else
    ok "Node.js $(node -v) already installed"
fi

# ── Step 3: Create NSO user and dirs ──
info "Setting up NSO directory structure..."
id -u $NSO_USER &>/dev/null || useradd --system --shell /usr/sbin/nologin --home-dir $NSO_DIR --create-home $NSO_USER
mkdir -p $NSO_DIR/{data,config,workspaces,venv,vm,repo}
ok "Directory structure ready"

# ── Step 4: Python venv ──
info "Setting up Python environment..."
python3 -m venv $NSO_DIR/venv
$NSO_DIR/venv/bin/pip install --upgrade pip -q
$NSO_DIR/venv/bin/pip install -q \
    fastapi uvicorn httpx asyncpg pydantic aiofiles python-multipart pyyaml websockets
ok "Python environment ready"

# ── Step 5: Download agent code ──
info "Downloading NSO agent..."
AGENT_URL="${NSO_HOST}/api/download/agent"
DOWNLOAD_OK=false

# Try downloading from platform
if curl -fsSL --max-time 30 "$AGENT_URL" -o /tmp/nso-agent.tar.gz 2>/dev/null; then
    tar -xzf /tmp/nso-agent.tar.gz -C $NSO_DIR/vm/ 2>/dev/null && DOWNLOAD_OK=true
    rm -f /tmp/nso-agent.tar.gz
fi

# Fallback: clone from GitHub
if [[ "$DOWNLOAD_OK" != "true" ]]; then
    warn "Download from platform failed, cloning from GitHub..."
    if [[ -d "$NSO_DIR/repo/.git" ]]; then
        cd $NSO_DIR/repo && git pull -q origin main 2>/dev/null || true
    else
        git clone -q https://github.com/lailaelghazouanitecnologia-cloud/setupo.git $NSO_DIR/repo 2>/dev/null || true
    fi
    if [[ -d "$NSO_DIR/repo/vm/agent" ]]; then
        cp -r $NSO_DIR/repo/vm/agent/* $NSO_DIR/vm/agent/ 2>/dev/null || true
        cp -r $NSO_DIR/repo/vm/cli $NSO_DIR/vm/cli 2>/dev/null || true
        cp $NSO_DIR/repo/vm/nso $NSO_DIR/vm/nso 2>/dev/null || true
        DOWNLOAD_OK=true
    fi
fi

[[ "$DOWNLOAD_OK" == "true" ]] || die "Failed to download agent code"
ok "Agent code installed"

# ── Step 6: Install CLI ──
info "Installing NSO CLI..."
if [[ -f "$NSO_DIR/vm/nso" ]]; then
    ln -sf $NSO_DIR/vm/nso /usr/local/bin/nso
    chmod +x $NSO_DIR/vm/nso
    ok "CLI installed: nso"
fi

# ── Step 7: Agent config ──
info "Configuring agent..."
cat > $NSO_DIR/config/agent.env << AGENT_ENV
NSO_ADMIN_EMAIL=${NSO_ADMIN_EMAIL}
AGENT_ADMIN_PASSWORD=${NSO_ADMIN_PASSWORD}
NSO_JWT_SECRET=${NSO_JWT_SECRET}
NSO_AGENT_HOST=127.0.0.1
NSO_AGENT_PORT=${NSO_AGENT_PORT}
NSO_CENTRAL_URL=${NSO_HOST}
${NSO_CENTRAL:+DATABASE_URL=${DATABASE_URL:-}}
AGENT_ENV
chmod 600 $NSO_DIR/config/agent.env
ok "Agent configured"

# ── Step 8: Nginx ──
info "Configuring nginx..."
SERVER_NAME="${NSO_DOMAIN:-_}"
cat > /etc/nginx/sites-available/nso << NGINX_CONF
server {
    listen 80 default_server;
    server_name ${SERVER_NAME};

    server_tokens off;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    location /agent/ {
        proxy_pass http://127.0.0.1:${NSO_AGENT_PORT}/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }

    location / {
        root /opt/nso/workspaces/default/static;
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX_CONF

ln -sf /etc/nginx/sites-available/nso /etc/nginx/sites-enabled/nso
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
ok "Nginx configured"

# ── Step 9: Systemd service ──
info "Creating systemd service..."
cat > /etc/systemd/system/nso-agent.service << SERVICE
[Unit]
Description=NSO Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${NSO_DIR}/vm/agent
EnvironmentFile=${NSO_DIR}/config/agent.env
ExecStart=${NSO_DIR}/venv/bin/uvicorn main:app --host 127.0.0.1 --port ${NSO_AGENT_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable nso-agent
ok "Systemd service created"

# ── Step 10: Fix ownership ──
chown -R root:root $NSO_DIR
chown root:root $NSO_DIR/config/agent.env

# ── Step 11: Create default workspace ──
mkdir -p $NSO_DIR/workspaces/default/static
cat > $NSO_DIR/workspaces/default/static/index.html << 'HTML'
<!DOCTYPE html>
<html>
<head>
    <title>NSO Instance</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e0e0e0;
               display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .card { text-align: center; padding: 3rem; border: 1px solid #222; border-radius: 12px; }
        h1 { color: #fff; margin-bottom: 0.5rem; }
        p { color: #888; }
        code { background: #1a1a1a; padding: 0.3rem 0.6rem; border-radius: 4px; font-size: 0.9rem; }
    </style>
</head>
<body>
    <div class="card">
        <h1>NSO Instance</h1>
        <p>Your server is ready. Deploy a workspace to get started.</p>
        <p><code>nso ship my-app this-instance</code></p>
    </div>
</body>
</html>
HTML

# ── Step 12: Firewall ──
info "Configuring firewall..."
ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1
ufw allow 22/tcp > /dev/null 2>&1
ufw allow 80/tcp > /dev/null 2>&1
ufw allow 443/tcp > /dev/null 2>&1
ufw --force enable > /dev/null 2>&1
ok "Firewall configured"

# ── Step 13: SSL (if domain is set) ──
if [[ -n "$NSO_DOMAIN" && "$NSO_DOMAIN" != "_" ]]; then
    info "Setting up SSL for ${NSO_DOMAIN}..."
    certbot --nginx -d "$NSO_DOMAIN" --non-interactive --agree-tos \
        ${NSO_ADMIN_EMAIL:+"-m $NSO_ADMIN_EMAIL"} \
        --register-unsafely-without-email 2>/dev/null || warn "SSL setup failed (will retry later)"
fi

# ── Step 14: Start agent ──
info "Starting NSO agent..."
systemctl start nso-agent
sleep 2

if systemctl is-active --quiet nso-agent; then
    ok "NSO agent is running"
else
    warn "Agent failed to start. Check: journalctl -u nso-agent"
fi

# ── Step 15: Register with platform ──
if [[ -n "$NSO_TOKEN" ]]; then
    info "Registering with NSO platform..."
    REGISTER_DATA=$(cat <<JSON
{
    "ip": "${SERVER_IP}",
    "agent_port": ${NSO_AGENT_PORT},
    "agent_password": "${NSO_ADMIN_PASSWORD}",
    "domain": "${NSO_DOMAIN}",
    "version": "${NSO_VERSION}"
}
JSON
)
    REGISTER_RESP=$(curl -fsSL --max-time 10 \
        -X POST "${NSO_HOST}/api/instances/register" \
        -H "Authorization: Bearer ${NSO_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$REGISTER_DATA" 2>/dev/null || true)

    if echo "$REGISTER_RESP" | jq -e '.ok' &>/dev/null; then
        ok "Registered with platform"
    else
        warn "Registration failed (you can register manually later)"
    fi
fi

# ── Done ──
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  NSO Agent installed successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo -e "  Server IP:   ${BLUE}${SERVER_IP}${NC}"
[[ -n "$NSO_DOMAIN" ]] && echo -e "  Domain:      ${BLUE}${NSO_DOMAIN}${NC}"
echo -e "  Agent:       ${BLUE}http://${SERVER_IP}:${NSO_AGENT_PORT}/health${NC}"
echo -e "  Admin pass:  ${YELLOW}${NSO_ADMIN_PASSWORD}${NC}"
if [[ "$NSO_CENTRAL" == "true" ]]; then
    echo -e "  DB URL:      ${YELLOW}${DATABASE_URL}${NC}"
    echo -e "  DB Password: ${YELLOW}${DB_PASSWORD}${NC}"
fi
echo ""
echo -e "  ${BLUE}Save this password — you'll need it to connect.${NC}"
echo ""
echo -e "  Quick start:"
echo -e "    nso login --host ${NSO_HOST}"
echo -e "    nso ship my-workspace this-instance"
echo ""
