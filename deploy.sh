#!/bin/bash
# MMS — Deploy / update script
# Usage: ./deploy.sh <server-ip> [ssh-key-path]
#
# Connects to the VPS, pulls latest code, installs deps,
# updates nginx config, and restarts both services.

set -euo pipefail

SERVER="${1:?Usage: ./deploy.sh <server-ip> [ssh-key-path]}"
SSH_KEY="${2:-~/.ssh/id_ed25519}"
SSH_USER="root"
REMOTE_DIR="/opt/mms"

ssh_cmd() {
    ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$SSH_USER@$SERVER" "$@"
}

scp_cmd() {
    scp -o StrictHostKeyChecking=no -i "$SSH_KEY" "$@"
}

echo "=== MMS deploy to $SERVER ==="

# ── 1. Pull latest code ─────────────────────────────────────
echo "[1/6] Pulling latest code..."
ssh_cmd "cd $REMOTE_DIR && git pull origin main" || {
    echo "git pull failed — trying full clone..."
    ssh_cmd "rm -rf ${REMOTE_DIR}/repo && git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git ${REMOTE_DIR}/repo"
    ssh_cmd "cp -r ${REMOTE_DIR}/repo/* ${REMOTE_DIR}/ && cp -r ${REMOTE_DIR}/repo/.* ${REMOTE_DIR}/ 2>/dev/null; rm -rf ${REMOTE_DIR}/repo"
}

# ── 2. Install Python deps ──────────────────────────────────
echo "[2/6] Installing Python dependencies..."
ssh_cmd "${REMOTE_DIR}/venv/bin/pip install -r ${REMOTE_DIR}/requirements.txt --quiet"
ssh_cmd "${REMOTE_DIR}/venv/bin/pip install -r ${REMOTE_DIR}/mms-metrics/requirements.txt --quiet"

# ── 3. Update nginx config ──────────────────────────────────
echo "[3/6] Updating nginx config..."
scp_cmd deploy/nginx.conf "$SSH_USER@$SERVER:/etc/nginx/sites-available/mms"
ssh_cmd "nginx -t && systemctl reload nginx"

# ── 4. Restart mms-metrics service ──────────────────────────
echo "[4/6] Restarting mms-metrics service..."
ssh_cmd "systemctl daemon-reload && systemctl restart mms-metrics"

# ── 5. Restart MMS main service ─────────────────────────────
echo "[5/6] Restarting MMS service..."
ssh_cmd "systemctl restart mms"

# ── 6. Verify ───────────────────────────────────────────────
echo "[6/6] Verifying..."
sleep 3
ssh_cmd "systemctl is-active mms && echo 'MMS API: OK' || echo 'MMS API: FAILED'"
ssh_cmd "systemctl is-active mms-metrics && echo 'MMS Metrics: OK' || echo 'MMS Metrics: FAILED'"
ssh_cmd "curl -sf http://127.0.0.1:8000/api/health && echo ' Health: OK' || echo ' Health: FAILED'"
ssh_cmd "curl -sf http://127.0.0.1:8081/health && echo ' Metrics Health: OK' || echo ' Metrics Health: FAILED'"

echo "=== Deploy complete ==="
