#!/bin/bash
set -euo pipefail
exec > /var/log/nso-init.log 2>&1

echo "===== NSO Platform Bootstrap ====="
echo "Started: $(date -u)"

# ── Variables injected by provisioner (via cloud-init userdata) ──
# These are replaced at deploy time — never committed with real values.
NSO_ADMIN_EMAIL="${NSO_ADMIN_EMAIL:-__NSO_ADMIN_EMAIL__}"
NSO_ADMIN_PASSWORD="${NSO_ADMIN_PASSWORD:-__NSO_ADMIN_PASSWORD__}"
AGENT_ADMIN_PASSWORD="${AGENT_ADMIN_PASSWORD:-__AGENT_ADMIN_PASSWORD__}"
VULTR_API_KEY="${VULTR_API_KEY:-__VULTR_API_KEY__}"
CF_API_TOKEN="${CF_API_TOKEN:-__CF_API_TOKEN__}"
CF_NSO_ZONE_ID="${CF_NSO_ZONE_ID:-__CF_NSO_ZONE_ID__}"
R2_ENDPOINT="${R2_ENDPOINT:-__R2_ENDPOINT__}"
R2_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:-__R2_ACCESS_KEY_ID__}"
R2_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:-__R2_SECRET_ACCESS_KEY__}"
R2_BUCKET="${R2_BUCKET:-nso}"
NSO_DOMAIN="${NSO_DOMAIN:-nso.dev}"
REPO_BRANCH="${REPO_BRANCH:-main}"

# ── 1. System packages ──────────────────────────────────────────
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y \
  nginx certbot python3-certbot-nginx \
  fail2ban ufw \
  python3 python3-venv python3-pip \
  git curl jq unzip tar

# Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
echo "Node $(node --version), npm $(npm --version)"

# ── 2. Firewall ─────────────────────────────────────────────────
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8081/tcp
ufw --force enable

# ── 3. Fail2ban ─────────────────────────────────────────────────
systemctl enable fail2ban
systemctl start fail2ban

# ── 4. NSO directories ─────────────────────────────────────────
mkdir -p /opt/nso/{data,config,workspaces,logs}
mkdir -p /opt/nso/client/{dashboard,admin}

# ── 5. Clone repo ──────────────────────────────────────────────
cd /opt/nso
if [ ! -d repo ]; then
  git clone -b "$REPO_BRANCH" https://github.com/lailaelghazouanitecnologia-cloud/setupo.git repo
fi
cp -r repo/nso /opt/nso/nso
cp -r repo/vm /opt/nso/vm
cp repo/requirements.txt /opt/nso/requirements.txt

# ── 6. Python venv ─────────────────────────────────────────────
python3 -m venv /opt/nso/venv
/opt/nso/venv/bin/pip install --upgrade pip
/opt/nso/venv/bin/pip install -r /opt/nso/requirements.txt

# ── 7. Environment variables ──────────────────────────────────
cat > /opt/nso/config/.env << ENVEOF
# Vultr
VULTR_API_KEY=${VULTR_API_KEY}
VULTR_DEFAULT_REGION=ewr
VULTR_DEFAULT_PLAN=vc2-1c-1gb
VULTR_DEFAULT_OS=2136

# Cloudflare
CF_API_TOKEN=${CF_API_TOKEN}
CF_NSO_ZONE_ID=${CF_NSO_ZONE_ID}
NSO_BASE_DOMAIN=${NSO_DOMAIN}

# R2 Storage
R2_ENDPOINT=${R2_ENDPOINT}
R2_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}
R2_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}
R2_BUCKET=${R2_BUCKET}

# Central Server
NSO_HOST=0.0.0.0
NSO_PORT=8000
NSO_CORS_ORIGINS=https://${NSO_DOMAIN},https://sonfazt.${NSO_DOMAIN},http://localhost:3000
NSO_DATA_DIR=/opt/nso/data
NSO_CONFIG_DIR=/opt/nso/config
NSO_WORKSPACES_DIR=/opt/nso/workspaces

# Admin
NSO_ADMIN_EMAIL=${NSO_ADMIN_EMAIL}
NSO_ADMIN_PASSWORD=${NSO_ADMIN_PASSWORD}

# Agent
AGENT_ADMIN_PASSWORD=${AGENT_ADMIN_PASSWORD}

# JWT — MUST be set so all uvicorn workers share the same secret
NSO_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ENVEOF
chmod 600 /opt/nso/config/.env

cat > /opt/nso/config/agent.env << AGENTEOF
NSO_ADMIN_EMAIL=${NSO_ADMIN_EMAIL}
AGENT_ADMIN_PASSWORD=${AGENT_ADMIN_PASSWORD}
NSO_AGENT_HOST=0.0.0.0
NSO_AGENT_PORT=8081
AGENTEOF
chmod 600 /opt/nso/config/agent.env

# ── 8. Build dashboards ──────────────────────────────────────
echo "Building main dashboard..."
cd /opt/nso/repo/client/dashboard
npm install --legacy-peer-deps
if npm run build; then
  cp -r out/* /opt/nso/client/dashboard/
  echo "Dashboard build OK"
else
  echo "Dashboard build FAILED — using placeholder"
  echo '<html><body><h1>NSO Dashboard</h1><p>Build failed — run platform-update to retry</p></body></html>' > /opt/nso/client/dashboard/index.html
fi

echo "Building admin dashboard..."
cd /opt/nso/repo/client/admin
npm install --legacy-peer-deps
if npm run build; then
  cp -r out/* /opt/nso/client/admin/
  echo "Admin dashboard build OK"
else
  echo "Admin dashboard build FAILED — using placeholder"
  echo '<html><body><h1>NSO Admin</h1><p>Build failed — run platform-update to retry</p></body></html>' > /opt/nso/client/admin/index.html
fi

# ── 9. Systemd services ─────────────────────────────────────
cat > /etc/systemd/system/nso.service << 'SVCEOF'
[Unit]
Description=NSO Central API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/nso
EnvironmentFile=/opt/nso/config/.env
ExecStart=/opt/nso/venv/bin/uvicorn nso.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/systemd/system/nso-agent.service << 'SVCEOF'
[Unit]
Description=NSO Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/nso/vm/agent
EnvironmentFile=/opt/nso/config/agent.env
Environment=PYTHONPATH=/opt/nso/vm/agent
ExecStart=/opt/nso/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8081 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable nso nso-agent
systemctl start nso nso-agent

# ── 10. Nginx config ────────────────────────────────────────
cat > /etc/nginx/sites-available/nso << NGINXEOF
server {
    listen 80 default_server;
    server_name ${NSO_DOMAIN} www.${NSO_DOMAIN} _;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400;
    }

    location /agent/ {
        rewrite ^/agent/(.*) /\$1 break;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }

    location / {
        root /opt/nso/client/dashboard;
        try_files \$uri \$uri/ /index.html;
    }
}

server {
    listen 80;
    server_name sonfazt.${NSO_DOMAIN};

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /agent/ {
        rewrite ^/agent/(.*) /\$1 break;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location / {
        root /opt/nso/client/admin;
        try_files \$uri \$uri/ /index.html;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/nso /etc/nginx/sites-enabled/nso
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 11. Update DNS to this IP ────────────────────────────────
MY_IP=$(curl -s https://api.ipify.org || curl -s https://ifconfig.me)
echo "Server IP: $MY_IP"

if [ -n "$CF_API_TOKEN" ] && [ "$CF_API_TOKEN" != "__CF_API_TOKEN__" ]; then
  echo "Updating DNS ${NSO_DOMAIN} → $MY_IP"

  # Find existing A record
  RECORD_ID=$(curl -s "https://api.cloudflare.com/client/v4/zones/${CF_NSO_ZONE_ID}/dns_records?name=${NSO_DOMAIN}&type=A" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" | jq -r '.result[0].id // empty')

  if [ -n "$RECORD_ID" ]; then
    # Update existing record
    curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/${CF_NSO_ZONE_ID}/dns_records/${RECORD_ID}" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"content\":\"${MY_IP}\",\"proxied\":false}" | jq '.success'
  else
    # Create new record
    curl -s -X POST "https://api.cloudflare.com/client/v4/zones/${CF_NSO_ZONE_ID}/dns_records" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"type\":\"A\",\"name\":\"${NSO_DOMAIN}\",\"content\":\"${MY_IP}\",\"ttl\":1,\"proxied\":false}" | jq '.success'
  fi

  # Also set sonfazt subdomain
  SUB_RECORD_ID=$(curl -s "https://api.cloudflare.com/client/v4/zones/${CF_NSO_ZONE_ID}/dns_records?name=sonfazt.${NSO_DOMAIN}&type=A" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" | jq -r '.result[0].id // empty')

  if [ -n "$SUB_RECORD_ID" ]; then
    curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/${CF_NSO_ZONE_ID}/dns_records/${SUB_RECORD_ID}" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"content\":\"${MY_IP}\",\"proxied\":false}" | jq '.success'
  else
    curl -s -X POST "https://api.cloudflare.com/client/v4/zones/${CF_NSO_ZONE_ID}/dns_records" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"type\":\"A\",\"name\":\"sonfazt.${NSO_DOMAIN}\",\"content\":\"${MY_IP}\",\"ttl\":1,\"proxied\":false}" | jq '.success'
  fi

  echo "DNS updated — waiting 10s for propagation"
  sleep 10
fi

# ── 12. SSL with certbot ─────────────────────────────────────
echo "Configuring SSL..."
certbot --nginx -d "${NSO_DOMAIN}" --non-interactive --agree-tos -m "${NSO_ADMIN_EMAIL}" || {
  echo "Certbot failed for ${NSO_DOMAIN} — will retry in 60s"
  sleep 60
  certbot --nginx -d "${NSO_DOMAIN}" --non-interactive --agree-tos -m "${NSO_ADMIN_EMAIL}" || echo "Certbot failed — SSL not configured"
}

# Try admin subdomain SSL too
certbot --nginx -d "sonfazt.${NSO_DOMAIN}" --non-interactive --agree-tos -m "${NSO_ADMIN_EMAIL}" || echo "Certbot for admin subdomain skipped"

# ── 13. Verify services ─────────────────────────────────────
echo ""
echo "===== Verification ====="
echo "NSO API:   $(curl -s http://127.0.0.1:8000/api/health | jq -r '.status // "FAIL"')"
echo "Agent:     $(curl -s http://127.0.0.1:8081/health | jq -r '.agent_version // "FAIL"')"
echo "Nginx:     $(systemctl is-active nginx)"
echo "Dashboard: $([ -f /opt/nso/client/dashboard/_next/static -o -d /opt/nso/client/dashboard/_next ] && echo 'BUILT' || echo 'PLACEHOLDER')"
echo ""
echo "===== NSO Bootstrap Complete ====="
echo "Finished: $(date -u)"
echo "Access: https://${NSO_DOMAIN}"
