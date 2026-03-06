#!/bin/bash
set -euo pipefail
exec > /var/log/nso-init.log 2>&1

echo "===== NSO Platform Bootstrap ====="
echo "Started: $(date -u)"

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
git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git repo
# Copy code into place
cp -r repo/nso /opt/nso/nso
cp -r repo/vm /opt/nso/vm
cp -r repo/client /opt/nso/client-src
cp repo/requirements.txt /opt/nso/requirements.txt

# ── 6. Python venv ─────────────────────────────────────────────
python3 -m venv /opt/nso/venv
/opt/nso/venv/bin/pip install --upgrade pip
/opt/nso/venv/bin/pip install -r /opt/nso/requirements.txt

# ── 7. Environment variables ───────────────────────────────────
cat > /opt/nso/config/.env << 'ENVEOF'
# Vultr
VULTR_API_KEY=HBAILFPFLQNQTNMCCJIPCTWZKDV2LAE5TD3Q
VULTR_DEFAULT_REGION=ewr
VULTR_DEFAULT_PLAN=vc2-1c-1gb
VULTR_DEFAULT_OS=2136

# Cloudflare
CF_API_TOKEN=FjJDBFCJAMVP-XUrLQiGAAvsKqOASpzT8nAMwAMF
CF_NSO_ZONE_ID=3e838f60e6da8e2fae4845b18673412d
NSO_BASE_DOMAIN=nso.dev

# R2 Storage
R2_ENDPOINT=https://1316bb77c9a6d0dde064e80f832c4594.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=8b8d05dbdd50fae36b9fb769158152c1
R2_SECRET_ACCESS_KEY=ea89632bf39197f33ce60c8127e028c4a048ccd8de64421e64012c9d653606cf
R2_BUCKET=nso

# Central Server
NSO_HOST=0.0.0.0
NSO_PORT=8000
NSO_CORS_ORIGINS=https://nso.dev,https://sonfazt.nso.dev,http://localhost:3000
NSO_DATA_DIR=/opt/nso/data
NSO_CONFIG_DIR=/opt/nso/config
NSO_WORKSPACES_DIR=/opt/nso/workspaces

# Admin
NSO_ADMIN_EMAIL=ayman_gha@hotmail.com
NSO_ADMIN_PASSWORD=td82uQHH8AgjkiMCmbMDjdA3AbjDI7hE

# Agent
AGENT_ADMIN_PASSWORD=td82uQHH8AgjkiMCmbMDjdA3AbjDI7hE
ENVEOF

chmod 600 /opt/nso/config/.env

# Agent env file (subset for agent)
cat > /opt/nso/config/agent.env << 'AGENTEOF'
NSO_ADMIN_EMAIL=ayman_gha@hotmail.com
AGENT_ADMIN_PASSWORD=td82uQHH8AgjkiMCmbMDjdA3AbjDI7hE
NSO_AGENT_HOST=0.0.0.0
NSO_AGENT_PORT=8081
AGENTEOF

chmod 600 /opt/nso/config/agent.env

# ── 8. Build dashboard ─────────────────────────────────────────
cd /opt/nso/client-src/dashboard
npm install --legacy-peer-deps
npm run build || true
cp -r out/* /opt/nso/client/dashboard/ 2>/dev/null || true

# Build admin dashboard
cd /opt/nso/client-src/admin
npm install --legacy-peer-deps
npm run build || true
cp -r out/* /opt/nso/client/admin/ 2>/dev/null || true

# Fallback: create minimal index.html if build failed
if [ ! -f /opt/nso/client/dashboard/index.html ]; then
  echo '<html><body><h1>NSO Dashboard</h1><p>Build pending</p></body></html>' > /opt/nso/client/dashboard/index.html
fi
if [ ! -f /opt/nso/client/admin/index.html ]; then
  echo '<html><body><h1>NSO Admin</h1><p>Build pending</p></body></html>' > /opt/nso/client/admin/index.html
fi

# ── 9. Systemd services ───────────────────────────────────────
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

# ── 10. Nginx config ──────────────────────────────────────────
cat > /etc/nginx/sites-available/nso << 'NGINXEOF'
server {
    listen 80;
    server_name nso.dev www.nso.dev;

    # API — Central Server
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    # Agent
    location /agent/ {
        rewrite ^/agent/(.*) /$1 break;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # Dashboard (static)
    location / {
        root /opt/nso/client/dashboard;
        try_files $uri $uri/ /index.html;
    }
}

# Admin panel on subdomain
server {
    listen 80;
    server_name sonfazt.nso.dev;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /agent/ {
        rewrite ^/agent/(.*) /$1 break;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / {
        root /opt/nso/client/admin;
        try_files $uri $uri/ /index.html;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/nso /etc/nginx/sites-enabled/nso
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 11. SSL will be configured after DNS points here ──────────
echo "===== NSO Bootstrap Complete ====="
echo "Finished: $(date -u)"
echo "Services: nso (8000), nso-agent (8081), nginx (80)"
echo "Next: point DNS to this IP, then run certbot"
