#!/bin/bash
# z86 setup script — run on the filesystem-prod VPS
# Installs z86 service + agent behind nginx
set -e

echo "=== z86 Object Storage Setup ==="
echo "Domain: z86.dev"

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

# Generate tokens if not in .env
if ! grep -q "Z86_ADMIN_TOKEN" /opt/nso/.env 2>/dev/null; then
    TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "" >> /opt/nso/.env
    echo "# z86 Storage" >> /opt/nso/.env
    echo "Z86_ADMIN_TOKEN=${TOKEN}" >> /opt/nso/.env
    echo "Z86_DATA_DIR=/data/z86" >> /opt/nso/.env
    echo "Z86_HOST=0.0.0.0" >> /opt/nso/.env
    echo "Z86_PORT=8082" >> /opt/nso/.env
    echo ""
    echo "Generated Z86_ADMIN_TOKEN: ${TOKEN}"
    echo "(Add this to your central server .env too)"
fi

if ! grep -q "Z86_AGENT_PASSWORD" /opt/nso/.env 2>/dev/null; then
    AGENT_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    echo "Z86_AGENT_PASSWORD=${AGENT_PASS}" >> /opt/nso/.env
    echo "Z86_AGENT_PORT=8083" >> /opt/nso/.env
    echo ""
    echo "Generated Z86_AGENT_PASSWORD: ${AGENT_PASS}"
fi

# Install systemd services
cp /opt/nso/doc/deploy/z86.service /etc/systemd/system/z86.service
cp /opt/nso/doc/deploy/z86-agent.service /etc/systemd/system/z86-agent.service
systemctl daemon-reload

systemctl enable z86 z86-agent
systemctl start z86
systemctl start z86-agent
echo "z86 + z86-agent services started"

# Build z86 dashboard
echo "Building z86 dashboard..."
if [ -d /opt/nso/client/z86 ]; then
    # Install Node.js if needed
    if ! command -v node &> /dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y nodejs
    fi
    cd /opt/nso/client/z86
    npm install
    npm run export
    echo "Dashboard built at /opt/nso/client/z86/static/"
else
    echo "WARNING: /opt/nso/client/z86 not found, skipping dashboard build"
fi

# Install nginx config
apt-get install -y nginx > /dev/null 2>&1 || true
cp /opt/nso/doc/deploy/nginx-z86.conf /etc/nginx/sites-available/z86
ln -sf /etc/nginx/sites-available/z86 /etc/nginx/sites-enabled/z86
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
echo "nginx configured for z86.dev"

# SSL certificate
echo "Setting up SSL for z86.dev..."
if ! [ -f /etc/letsencrypt/live/z86.dev/fullchain.pem ]; then
    apt-get install -y certbot python3-certbot-nginx > /dev/null 2>&1 || true
    certbot --nginx -d z86.dev -d s3.z86.dev --non-interactive --agree-tos --email admin@nso.dev || echo "SSL setup failed — run certbot manually after DNS is configured"
fi

echo ""
echo "=== z86 is running ==="
echo ""
echo "Services:"
echo "  z86 storage:   http://localhost:8082/health"
echo "  z86 agent:     http://localhost:8083/health"
echo ""
echo "URLs:"
echo "  Dashboard:     https://z86.dev"
echo "  S3 API:        https://s3.z86.dev/{bucket}/{key}"
echo "  Agent:         https://z86.dev/agent/"
echo ""
echo "IMPORTANT — Add these to your central server .env:"
Z86_TOKEN=$(grep Z86_ADMIN_TOKEN /opt/nso/.env | cut -d= -f2)
Z86_AGENT_PASS=$(grep Z86_AGENT_PASSWORD /opt/nso/.env | cut -d= -f2)
echo "  Z86_ENDPOINT=https://s3.z86.dev"
echo "  Z86_ADMIN_TOKEN=${Z86_TOKEN}"
echo "  Z86_AGENT_ENDPOINT=https://z86.dev/agent"
echo "  Z86_AGENT_PASSWORD=${Z86_AGENT_PASS}"
echo ""
echo "DNS — Point these records to $(hostname -I | awk '{print $1}'):"
echo "  z86.dev     → A record"
echo "  s3.z86.dev  → A record"
