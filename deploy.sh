#!/bin/bash
# Setupo — Deploy / update script
# Usage: ./deploy.sh <server-ip> [ssh-key-path]
#
# Connects to the VPS, pulls latest code, installs deps,
# updates nginx config, and restarts the service.

set -euo pipefail

SERVER="${1:?Usage: ./deploy.sh <server-ip> [ssh-key-path]}"
SSH_KEY="${2:-~/.ssh/id_ed25519}"
SSH_USER="root"
REMOTE_DIR="/opt/setupo"

ssh_cmd() {
    ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$SSH_USER@$SERVER" "$@"
}

scp_cmd() {
    scp -o StrictHostKeyChecking=no -i "$SSH_KEY" "$@"
}

echo "=== Setupo deploy to $SERVER ==="

# ── 1. Pull latest code ─────────────────────────────────────
echo "[1/5] Pulling latest code..."
ssh_cmd "cd $REMOTE_DIR && git pull origin main" || {
    echo "git pull failed — trying full clone..."
    ssh_cmd "rm -rf ${REMOTE_DIR}/repo && git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git ${REMOTE_DIR}/repo"
    ssh_cmd "cp -r ${REMOTE_DIR}/repo/* ${REMOTE_DIR}/ && cp -r ${REMOTE_DIR}/repo/.* ${REMOTE_DIR}/ 2>/dev/null; rm -rf ${REMOTE_DIR}/repo"
}

# ── 2. Install Python deps ──────────────────────────────────
echo "[2/5] Installing Python dependencies..."
ssh_cmd "${REMOTE_DIR}/venv/bin/pip install -r ${REMOTE_DIR}/requirements.txt --quiet"

# ── 3. Update nginx config ──────────────────────────────────
echo "[3/5] Updating nginx config..."
scp_cmd deploy/nginx.conf "$SSH_USER@$SERVER:/etc/nginx/sites-available/setupo"
ssh_cmd "nginx -t && systemctl reload nginx"

# ── 4. Restart setupo service ───────────────────────────────
echo "[4/5] Restarting setupo service..."
ssh_cmd "systemctl daemon-reload && systemctl restart setupo"

# ── 5. Verify ───────────────────────────────────────────────
echo "[5/5] Verifying..."
sleep 3
ssh_cmd "systemctl is-active setupo && echo 'Service: OK' || echo 'Service: FAILED'"
ssh_cmd "curl -sf http://127.0.0.1:8000/api/health && echo ' Health: OK' || echo ' Health: FAILED'"

echo "=== Deploy complete ==="
