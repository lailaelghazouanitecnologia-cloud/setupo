#!/bin/bash
# z86 setup script — run on the filesystem-prod VPS
# Installs z86 as a systemd service behind nginx
set -e

echo "=== z86 Object Storage Setup ==="

# Create data directory
mkdir -p /data/z86/buckets
echo "Created /data/z86/buckets"

# Ensure code is deployed at /opt/nso
if [ ! -d /opt/nso/z86 ]; then
    echo "ERROR: /opt/nso/z86 not found. Deploy the codebase first."
    exit 1
fi

# Create venv if needed
if [ ! -d /opt/nso/venv ]; then
    python3 -m venv /opt/nso/venv
    /opt/nso/venv/bin/pip install -U pip
fi

# Install dependencies
/opt/nso/venv/bin/pip install fastapi uvicorn aiosqlite httpx

# Generate admin token if not in .env
if ! grep -q "Z86_ADMIN_TOKEN" /opt/nso/.env 2>/dev/null; then
    TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "" >> /opt/nso/.env
    echo "Z86_ADMIN_TOKEN=${TOKEN}" >> /opt/nso/.env
    echo "Z86_DATA_DIR=/data/z86" >> /opt/nso/.env
    echo "Generated Z86_ADMIN_TOKEN (add this to your central server .env too)"
    echo "Token: ${TOKEN}"
fi

# Install systemd service
cp /opt/nso/doc/deploy/z86.service /etc/systemd/system/z86.service
systemctl daemon-reload
systemctl enable z86
systemctl start z86
echo "z86 service started"

# Install nginx config
cp /opt/nso/doc/deploy/nginx-z86.conf /etc/nginx/sites-available/z86
ln -sf /etc/nginx/sites-available/z86 /etc/nginx/sites-enabled/z86
nginx -t && systemctl reload nginx
echo "nginx configured"

echo ""
echo "=== z86 is running ==="
echo "Health: curl http://localhost:8082/health"
echo "Admin:  curl -H 'Authorization: Bearer \$Z86_ADMIN_TOKEN' http://localhost:8082/admin/stats"
echo ""
echo "IMPORTANT: Add these to your central server .env:"
echo "  Z86_ENDPOINT=http://$(hostname -I | awk '{print $1}'):8082"
echo "  Z86_ADMIN_TOKEN=<the token above>"
echo "  Z86_BUCKET=nso"
