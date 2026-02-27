#!/bin/bash
# ═══════════════════════════════════════════════════
# NSO (Setupo) — Full bootstrap for fresh Debian 12
# Run as root on the new VPS
# ═══════════════════════════════════════════════════
set -euo pipefail

REPO="https://github.com/lailaelghazouanitecnologia-cloud/setupo.git"
APP_DIR="/opt/setupo"
LOG="/var/log/setupo-bootstrap.log"

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
mkdir -p /var/log/setupo
chmod 755 "$APP_DIR"

# ── 4. Python environment ────────────────────────
log "[4/8] Setting up Python virtual environment..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/nso-agent/requirements.txt" --quiet

# ── 5. Build dashboard ──────────────────────────
log "[5/8] Building dashboard..."
cd "$APP_DIR/dashboard"
npm install --silent 2>/dev/null || true
npx next build
mkdir -p "$APP_DIR/dashboard/static"
cp -r "$APP_DIR/dashboard/out/"* "$APP_DIR/dashboard/static/"

# ── 6. Environment file ─────────────────────────
log "[6/8] Setting up environment..."
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  log "  -> Created .env from example — EDIT IT with your keys!"
fi
chmod 600 "$APP_DIR/.env"

# ── 7. Systemd services ─────────────────────────
log "[7/8] Installing systemd services..."
cp "$APP_DIR/deploy/setupo.service" /etc/systemd/system/setupo.service
cp "$APP_DIR/deploy/setupo-agent.service" /etc/systemd/system/setupo-agent.service

systemctl daemon-reload
systemctl enable setupo-agent setupo
systemctl start setupo-agent
sleep 2
systemctl start setupo

# ── 8. Nginx ─────────────────────────────────────
log "[8/8] Configuring nginx..."
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/setupo
ln -sf /etc/nginx/sites-available/setupo /etc/nginx/sites-enabled/setupo
rm -f /etc/nginx/sites-enabled/default

# Test nginx config — if SSL certs don't exist yet, use HTTP-only temporarily
if nginx -t 2>/dev/null; then
  systemctl reload nginx
else
  log "  -> Nginx config has SSL refs but certs don't exist yet."
  log "  -> Creating temporary HTTP-only config..."
  cat > /etc/nginx/sites-available/setupo-temp <<'NGINX'
upstream setupo_api { server 127.0.0.1:8000; }
upstream setupo_agent { server 127.0.0.1:8081; }
server {
    listen 80;
    server_name _;
    location /api/ {
        proxy_pass http://setupo_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
    location /agent/ {
        proxy_pass http://setupo_agent/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location / {
        root /opt/setupo/dashboard/static;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
NGINX
  ln -sf /etc/nginx/sites-available/setupo-temp /etc/nginx/sites-enabled/setupo
  nginx -t && systemctl reload nginx
  log "  -> HTTP-only nginx running. Run certbot to enable HTTPS:"
  log "     certbot --nginx -d zarnetti.com"
fi

# ── Done ─────────────────────────────────────────
log ""
log "=== Bootstrap complete ==="
log ""
log "Services:"
systemctl is-active setupo-agent && log "  setupo-agent: OK" || log "  setupo-agent: FAILED"
systemctl is-active setupo && log "  setupo: OK" || log "  setupo: FAILED"
systemctl is-active nginx && log "  nginx: OK" || log "  nginx: FAILED"
log ""
log "Next steps:"
log "  1. Edit /opt/setupo/.env with your API keys"
log "  2. Run: certbot --nginx -d zarnetti.com"
log "  3. Restart: systemctl restart setupo setupo-agent"
log "  4. Visit: https://zarnetti.com"
