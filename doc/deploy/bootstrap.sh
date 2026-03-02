#!/bin/bash
# ═══════════════════════════════════════════════════
# NSO — Full bootstrap for fresh Debian 12
# Run as root on the new VPS
# ═══════════════════════════════════════════════════
set -euo pipefail

REPO="https://github.com/lailaelghazouanitecnologia-cloud/setupo.git"
APP_DIR="/opt/nso"
LOG="/var/log/nso-bootstrap.log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

log "=== NSO Bootstrap starting ==="

# ── 1. System packages ────────────────────────────
log "[1/8] Installing system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
  python3 python3-pip python3-venv \
  nginx certbot python3-certbot-nginx \
  git curl jq ca-certificates ufw \
  rsync nodejs npm

# ── 2. Firewall ──────────────────────────────────
log "[2/8] Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8081/tcp
ufw --force enable

# ── 3. Clone repo ────────────────────────────────
log "[3/8] Cloning repository..."
mkdir -p "$APP_DIR"
GIT_BRANCH="${GIT_BRANCH:-claude/zarnight-3YWf0}"
if [ -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR" && git fetch origin "$GIT_BRANCH" && git checkout "$GIT_BRANCH" && git pull origin "$GIT_BRANCH"
else
  git clone -b "$GIT_BRANCH" "$REPO" "$APP_DIR"
fi

# Create data dirs
mkdir -p "$APP_DIR"/{data,config,workspaces}
mkdir -p /var/log/nso
chmod 755 "$APP_DIR"

# ── 4. Python environment ────────────────────────
log "[4/8] Setting up Python virtual environment..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/instance/requirements.txt" --quiet

# ── 5. Build dashboards ─────────────────────────
log "[5/9] Building main dashboard..."
cd "$APP_DIR/client/dashboard"
npm install --silent 2>/dev/null || true
npx next build
mkdir -p "$APP_DIR/client/dashboard/static"
cp -r "$APP_DIR/client/dashboard/out/"* "$APP_DIR/client/dashboard/static/"

log "[5/9] Building admin dashboard..."
cd "$APP_DIR/client/admin"
npm install --silent 2>/dev/null || true
npx next build
mkdir -p "$APP_DIR/client/admin/static"
cp -r "$APP_DIR/client/admin/out/"* "$APP_DIR/client/admin/static/"

# ── 6. Environment file ─────────────────────────
log "[6/8] Setting up environment..."
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  log "  -> Created .env from example — EDIT IT with your keys!"
fi
chmod 600 "$APP_DIR/.env"

# ── 7. Systemd services ─────────────────────────
log "[7/8] Installing systemd services..."
cp "$APP_DIR/doc/deploy/nso.service" /etc/systemd/system/nso.service
cp "$APP_DIR/doc/deploy/nso-agent.service" /etc/systemd/system/nso-agent.service

systemctl daemon-reload
systemctl enable nso-agent nso
systemctl start nso-agent
sleep 2
systemctl start nso

# ── 8. Nginx ─────────────────────────────────────
log "[8/8] Configuring nginx..."
cp "$APP_DIR/doc/deploy/nginx.conf" /etc/nginx/sites-available/nso
ln -sf /etc/nginx/sites-available/nso /etc/nginx/sites-enabled/nso
rm -f /etc/nginx/sites-enabled/default

# Test nginx config — if SSL certs don't exist yet, use HTTP-only temporarily
if nginx -t 2>/dev/null; then
  systemctl reload nginx
else
  log "  -> Nginx config has SSL refs but certs don't exist yet."
  log "  -> Creating temporary HTTP-only config..."
  cat > /etc/nginx/sites-available/nso-temp <<'NGINX'
upstream nso_api { server 127.0.0.1:8000; }
upstream nso_agent { server 127.0.0.1:8081; }
server {
    listen 80;
    server_name _;
    location /api/ {
        proxy_pass http://nso_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
    location /agent/ {
        proxy_pass http://nso_agent/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location / {
        root /opt/nso/client/dashboard/static;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
NGINX
  ln -sf /etc/nginx/sites-available/nso-temp /etc/nginx/sites-enabled/nso
  nginx -t && systemctl reload nginx
  log "  -> HTTP-only nginx running. Run certbot to enable HTTPS:"
  log "     certbot --nginx -d nso.dev"
fi

# ── Done ─────────────────────────────────────────
log ""
log "=== Bootstrap complete ==="
log ""
log "Services:"
systemctl is-active nso-agent && log "  nso-agent: OK" || log "  nso-agent: FAILED"
systemctl is-active nso && log "  nso: OK" || log "  nso: FAILED"
systemctl is-active nginx && log "  nginx: OK" || log "  nginx: FAILED"
log ""
log "Next steps:"
log "  1. Edit /opt/nso/.env with your API keys"
log "  2. Run: certbot --nginx -d nso.dev"
log "  3. Restart: systemctl restart nso nso-agent"
log "  4. Visit: https://nso.dev"
