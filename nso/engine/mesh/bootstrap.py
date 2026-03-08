"""
Generate device-specific bootstrap scripts for NSO Mesh.

The install script is served via GET /mesh/install/{token} and:
1. Installs Python + deps
2. Downloads and sets up the NSO agent
3. Configures SSH authorized_keys with Central's master public key
4. Starts the agent via systemd
5. Calls back to Central to activate the device
"""

import logging

from nso.config import settings
from nso.shared import db
from nso.shared.errors import NsoError
from nso.engine.mesh.service import ensure_master_key

logger = logging.getLogger("nso.mesh.bootstrap")

_INSTALL_TEMPLATE = """#!/bin/bash
# ─────────────────────────────────────────────────────────
# NSO Mesh — Device Bootstrap Script
# Generated for device: {device_name} ({device_id})
# One-time use — token expires after activation
# ─────────────────────────────────────────────────────────
set -euo pipefail

CENTRAL_URL="{central_url}"
DEVICE_ID="{device_id}"
DEVICE_TOKEN="{install_token}"
SSH_PUBKEY="{ssh_pubkey}"

echo "══════════════════════════════════════════════════════"
echo "  NSO Mesh — Installing agent on this device"
echo "══════════════════════════════════════════════════════"

# ── 1. System dependencies ──────────────────────────────
echo "[1/6] Installing system dependencies..."
if command -v apt-get &>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv curl tar
elif command -v yum &>/dev/null; then
    yum install -y -q python3 python3-pip curl tar
elif command -v apk &>/dev/null; then
    apk add --quiet python3 py3-pip curl tar
else
    echo "ERROR: Unsupported package manager. Install python3, pip, curl manually."
    exit 1
fi

# ── 2. SSH key setup ────────────────────────────────────
echo "[2/6] Configuring SSH access for NSO Central..."
mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Add Central's public key (idempotent)
if ! grep -qF "$SSH_PUBKEY" /root/.ssh/authorized_keys 2>/dev/null; then
    echo "$SSH_PUBKEY" >> /root/.ssh/authorized_keys
fi
chmod 600 /root/.ssh/authorized_keys

# ── 3. Download agent ───────────────────────────────────
echo "[3/6] Downloading NSO agent..."
mkdir -p /opt/nso/vm
curl -fsSL "$CENTRAL_URL/api/download/agent" -o /tmp/nso-agent.tar.gz
tar xzf /tmp/nso-agent.tar.gz -C /opt/nso/vm/
rm -f /tmp/nso-agent.tar.gz

# ── 4. Python venv + deps ──────────────────────────────
echo "[4/6] Setting up Python environment..."
python3 -m venv /opt/nso/venv
/opt/nso/venv/bin/pip install -q --upgrade pip
/opt/nso/venv/bin/pip install -q fastapi uvicorn aiosqlite httpx

# ── 5. Systemd service ─────────────────────────────────
echo "[5/6] Creating systemd service..."
cat > /etc/systemd/system/nso-agent.service << 'SVCEOF'
[Unit]
Description=NSO Agent
After=network.target

[Service]
Type=simple
ExecStart=/opt/nso/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8081
WorkingDirectory=/opt/nso/vm/agent
Restart=always
RestartSec=5
Environment=AGENT_ADMIN_PASSWORD={agent_password}

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable --now nso-agent

# Wait for agent to be ready
sleep 2

# ── 6. Callback to Central ─────────────────────────────
echo "[6/6] Registering device with NSO Central..."
FINGERPRINT=""
if [ -f /etc/ssh/ssh_host_ed25519_key.pub ]; then
    FINGERPRINT=$(ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub | awk '{{print $2}}')
fi
OS_INFO=$(uname -srm)
AGENT_VERSION="0.1.0"

HTTP_CODE=$(curl -s -o /tmp/nso-activate-response.json -w "%{{http_code}}" \\
    -X POST "$CENTRAL_URL/api/mesh/devices/$DEVICE_ID/activate" \\
    -H "Content-Type: application/json" \\
    -d "$(cat <<JSONEOF
{{
    "token": "$DEVICE_TOKEN",
    "fingerprint": "$FINGERPRINT",
    "os": "$OS_INFO",
    "agent_version": "$AGENT_VERSION"
}}
JSONEOF
)")

if [ "$HTTP_CODE" -eq 200 ]; then
    echo ""
    echo "══════════════════════════════════════════════════════"
    echo "  ✓ NSO Agent installed and registered successfully"
    echo "  Device: {device_name} ({device_id})"
    echo "  Agent running on port 8081"
    echo "══════════════════════════════════════════════════════"
else
    echo ""
    echo "WARNING: Device activation callback failed (HTTP $HTTP_CODE)"
    echo "Response: $(cat /tmp/nso-activate-response.json 2>/dev/null)"
    echo "The agent is running, but you may need to activate manually."
fi

rm -f /tmp/nso-activate-response.json
"""


async def generate_install_script(install_token: str) -> str:
    """Generate a device-specific install script from the one-time token."""
    # Find device by token
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM mesh_devices WHERE install_token = ?",
        (install_token,),
    )
    row = await cursor.fetchone()
    if not row:
        raise NsoError("Invalid or expired install token", 404)

    device = db._row_to_dict(row)

    if device["status"] not in ("pending", "provisioning", "error"):
        raise NsoError("Device already activated", 400)

    # Ensure master SSH key exists
    pubkey = await ensure_master_key()

    # Determine central URL
    central_url = f"https://{settings.NSO_BASE_DOMAIN}"

    # Update device status to provisioning
    await db.update("mesh_devices", device["id"], {"status": "provisioning"})

    script = _INSTALL_TEMPLATE.format(
        device_name=device["name"],
        device_id=device["id"],
        install_token=install_token,
        central_url=central_url,
        ssh_pubkey=pubkey,
        agent_password=settings.AGENT_ADMIN_PASSWORD or "changeme",
    )

    logger.info("Generated install script for device %s (%s)",
                device["name"], device["id"])
    return script
