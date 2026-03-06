#!/bin/bash
exec > /var/log/nso-init.log 2>&1
set -x

echo "===== NSO Lean Bootstrap ====="
echo "Started: $(date -u)"

export DEBIAN_FRONTEND=noninteractive

# ── 1. System packages (skip upgrade — too slow) ────────────
apt-get update -y
apt-get install -y nginx python3 python3-venv python3-pip git curl ufw || true

# ── 2. Firewall ─────────────────────────────────────────────
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8081/tcp
ufw --force enable || true

# ── 3. NSO directories ─────────────────────────────────────
mkdir -p /opt/nso/{data,config,workspaces,logs}
mkdir -p /opt/nso/client/{dashboard,admin}

# ── 4. Clone repo ──────────────────────────────────────────
cd /opt/nso
if [ ! -d repo ]; then
  git clone --depth 1 -b claude/analyze-codebase-nHGXt https://github.com/lailaelghazouanitecnologia-cloud/setupo.git repo
fi
cp -r repo/nso /opt/nso/nso
cp -r repo/vm /opt/nso/vm
cp repo/requirements.txt /opt/nso/requirements.txt

# ── 5. Python venv ─────────────────────────────────────────
python3 -m venv /opt/nso/venv
/opt/nso/venv/bin/pip install --upgrade pip
/opt/nso/venv/bin/pip install -r /opt/nso/requirements.txt

# ── 6. Environment variables ──────────────────────────────
cat > /opt/nso/config/.env << 'ENVEOF'
VULTR_API_KEY=HBAILFPFLQNQTNMCCJIPCTWZKDV2LAE5TD3Q
VULTR_DEFAULT_REGION=ewr
VULTR_DEFAULT_PLAN=vc2-1c-1gb
VULTR_DEFAULT_OS=2136
CF_API_TOKEN=FjJDBFCJAMVP-XUrLQiGAAvsKqOASpzT8nAMwAMF
CF_NSO_ZONE_ID=3e838f60e6da8e2fae4845b18673412d
NSO_BASE_DOMAIN=nso.dev
R2_ENDPOINT=https://1316bb77c9a6d0dde064e80f832c4594.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=8b8d05dbdd50fae36b9fb769158152c1
R2_SECRET_ACCESS_KEY=ea89632bf39197f33ce60c8127e028c4a048ccd8de64421e64012c9d653606cf
R2_BUCKET=nso
NSO_HOST=0.0.0.0
NSO_PORT=8000
NSO_CORS_ORIGINS=https://nso.dev,https://sonfazt.nso.dev,http://localhost:3000
NSO_DATA_DIR=/opt/nso/data
NSO_CONFIG_DIR=/opt/nso/config
NSO_WORKSPACES_DIR=/opt/nso/workspaces
NSO_ADMIN_EMAIL=ayman_gha@hotmail.com
NSO_ADMIN_PASSWORD=td82uQHH8AgjkiMCmbMDjdA3AbjDI7hE
AGENT_ADMIN_PASSWORD=td82uQHH8AgjkiMCmbMDjdA3AbjDI7hE
ENVEOF
chmod 600 /opt/nso/config/.env

cat > /opt/nso/config/agent.env << 'AGENTEOF'
NSO_ADMIN_EMAIL=ayman_gha@hotmail.com
AGENT_ADMIN_PASSWORD=td82uQHH8AgjkiMCmbMDjdA3AbjDI7hE
NSO_AGENT_HOST=0.0.0.0
NSO_AGENT_PORT=8081
AGENTEOF
chmod 600 /opt/nso/config/agent.env

# ── 7. Placeholder dashboards ─────────────────────────────
echo '<html><body><h1>NSO Dashboard</h1><p>Loading...</p></body></html>' > /opt/nso/client/dashboard/index.html
echo '<html><body><h1>NSO Admin</h1><p>Loading...</p></body></html>' > /opt/nso/client/admin/index.html

# ── 8. Systemd services ───────────────────────────────────
cat > /etc/systemd/system/nso.service << 'EOF'
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
EOF

cat > /etc/systemd/system/nso-agent.service << 'EOF'
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
EOF

systemctl daemon-reload
systemctl enable nso nso-agent
systemctl start nso nso-agent

# ── 9. Nginx config ──────────────────────────────────────
cat > /etc/nginx/sites-available/nso << 'EOF'
server {
    listen 80 default_server;
    server_name nso.dev www.nso.dev _;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    location /agent/ {
        rewrite ^/agent/(.*) /$1 break;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    location / {
        root /opt/nso/client/dashboard;
        try_files $uri $uri/ /index.html;
    }
}

server {
    listen 80;
    server_name sonfazt.nso.dev;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /agent/ {
        rewrite ^/agent/(.*) /$1 break;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        root /opt/nso/client/admin;
        try_files $uri $uri/ /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/nso /etc/nginx/sites-enabled/nso
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "===== NSO Bootstrap Complete ====="
echo "Finished: $(date -u)"
