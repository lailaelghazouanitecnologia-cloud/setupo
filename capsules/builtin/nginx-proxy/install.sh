#!/bin/bash
# Capsule: nginx-proxy - Install nginx reverse proxy
set -euo pipefail

apt-get update -qq
apt-get install -y -qq nginx

cat > /etc/nginx/sites-available/proxy <<'EOF'
server {
    listen 80;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

ln -sf /etc/nginx/sites-available/proxy /etc/nginx/sites-enabled/proxy
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

echo "nginx-proxy capsule installed"
