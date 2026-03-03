#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# NSO — Provision a new VPS instance (Vultr + Cloudflare DNS)
#
# Usage:
#   ./provision.sh <env>          # env = prod | test
#   ./provision.sh test --dry-run # preview without creating
#
# Requires these env vars (or source .env):
#   VULTR_API_KEY, CF_API_TOKEN, CF_NSO_ZONE_ID,
#   R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
#   NSO_ADMIN_EMAIL, NSO_ADMIN_PASSWORD
#
# Optional:
#   SSH_KEY_ID   — Vultr SSH key ID to attach
#   JWT_SECRET   — fixed JWT secret (auto-generated if unset)
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENVS_FILE="$SCRIPT_DIR/environments.json"
CLOUD_INIT="$PROJECT_ROOT/server/base/cloud-init.yaml"

# ── Args ──────────────────────────────────────────────────────
ENV_NAME="${1:-}"
DRY_RUN=false
[[ "${2:-}" == "--dry-run" ]] && DRY_RUN=true

if [[ -z "$ENV_NAME" ]]; then
  echo "Usage: $0 <env> [--dry-run]"
  echo "Available environments:"
  python3 -c "import json; [print(f'  {k}: {v[\"label\"]} ({v[\"domain\"]})') for k,v in json.load(open('$ENVS_FILE')).items()]"
  exit 1
fi

# ── Load env config ───────────────────────────────────────────
ENV_CFG=$(python3 -c "
import json, sys
envs = json.load(open('$ENVS_FILE'))
if '$ENV_NAME' not in envs:
    print(f'Error: unknown environment \"$ENV_NAME\"', file=sys.stderr)
    print(f'Available: {list(envs.keys())}', file=sys.stderr)
    sys.exit(1)
import json as j
print(j.dumps(envs['$ENV_NAME']))
")

LABEL=$(echo "$ENV_CFG" | python3 -c "import json,sys; print(json.load(sys.stdin)['label'])")
DOMAIN=$(echo "$ENV_CFG" | python3 -c "import json,sys; print(json.load(sys.stdin)['domain'])")
REGION=$(echo "$ENV_CFG" | python3 -c "import json,sys; print(json.load(sys.stdin)['region'])")
PLAN=$(echo "$ENV_CFG" | python3 -c "import json,sys; print(json.load(sys.stdin)['plan'])")
OS_ID=$(echo "$ENV_CFG" | python3 -c "import json,sys; print(json.load(sys.stdin)['os_id'])")
GIT_BRANCH=$(echo "$ENV_CFG" | python3 -c "import json,sys; print(json.load(sys.stdin)['git_branch'])")
BACKUPS=$(echo "$ENV_CFG" | python3 -c "import json,sys; print(json.load(sys.stdin)['backups'])")

# ── Validate required env vars ────────────────────────────────
for var in VULTR_API_KEY CF_API_TOKEN CF_NSO_ZONE_ID R2_ENDPOINT R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY NSO_ADMIN_EMAIL NSO_ADMIN_PASSWORD; do
  if [[ -z "${!var:-}" ]]; then
    echo "Error: $var is not set"
    exit 1
  fi
done

JWT_SECRET="${JWT_SECRET:-$(python3 -c "import secrets; print(secrets.token_hex(32))")}"
R2_BUCKET="${R2_BUCKET:-nso}"
R2_READY_BUCKET="${R2_READY_BUCKET:-nso-ready}"
SSH_KEY_ID="${SSH_KEY_ID:-}"

echo "═══════════════════════════════════════════════"
echo "NSO Provision: $ENV_NAME"
echo "═══════════════════════════════════════════════"
echo "  Label:      $LABEL"
echo "  Domain:     $DOMAIN"
echo "  Region:     $REGION"
echo "  Plan:       $PLAN"
echo "  OS:         Debian 12 ($OS_ID)"
echo "  Git branch: $GIT_BRANCH"
echo "  SSH key:    ${SSH_KEY_ID:-none}"
echo ""

if $DRY_RUN; then
  echo "[DRY RUN] Would create instance with above config."
  echo "[DRY RUN] Would update DNS for $DOMAIN."
  exit 0
fi

# ── Generate cloud-init ──────────────────────────────────────
echo "[1/4] Generating cloud-init..."
USER_DATA=$(python3 << PYEOF
import base64
with open("$CLOUD_INIT") as f:
    tpl = f.read()
replacements = {
    "{{DOMAIN}}": "$DOMAIN",
    "{{VULTR_API_KEY}}": "$VULTR_API_KEY",
    "{{CF_API_TOKEN}}": "$CF_API_TOKEN",
    "{{CF_NSO_ZONE_ID}}": "$CF_NSO_ZONE_ID",
    "{{ADMIN_EMAIL}}": "$NSO_ADMIN_EMAIL",
    "{{ADMIN_PASSWORD}}": "$NSO_ADMIN_PASSWORD",
    "{{JWT_SECRET}}": "$JWT_SECRET",
    "{{R2_ENDPOINT}}": "$R2_ENDPOINT",
    "{{R2_ACCESS_KEY_ID}}": "$R2_ACCESS_KEY_ID",
    "{{R2_SECRET_ACCESS_KEY}}": "$R2_SECRET_ACCESS_KEY",
    "{{R2_BUCKET}}": "$R2_BUCKET",
    "{{R2_READY_BUCKET}}": "$R2_READY_BUCKET",
    "{{GIT_BRANCH}}": "$GIT_BRANCH",
    "{{APP_GIT_URL}}": "",
    "{{APP_GIT_BRANCH}}": "main",
}
for old, new in replacements.items():
    tpl = tpl.replace(old, new)
# Verify no leftover placeholders
import re
leftovers = re.findall(r'\{\{[A-Z_]+\}\}', tpl)
if leftovers:
    import sys
    print(f"ERROR: unresolved placeholders: {leftovers}", file=sys.stderr)
    sys.exit(1)
print(base64.b64encode(tpl.encode()).decode())
PYEOF
)

echo "  Cloud-init generated ($(echo -n "$USER_DATA" | wc -c) bytes base64)"

# ── Create instance ──────────────────────────────────────────
echo "[2/4] Creating Vultr instance..."

SSH_ARRAY="[]"
if [[ -n "$SSH_KEY_ID" ]]; then
  SSH_ARRAY="[\"$SSH_KEY_ID\"]"
fi

RESULT=$(curl -s -X POST \
  -H "Authorization: Bearer $VULTR_API_KEY" \
  -H "Content-Type: application/json" \
  "https://api.vultr.com/v2/instances" \
  -d "{
    \"region\": \"$REGION\",
    \"plan\": \"$PLAN\",
    \"os_id\": $OS_ID,
    \"label\": \"$LABEL\",
    \"tag\": \"nso\",
    \"sshkey_id\": $SSH_ARRAY,
    \"user_data\": \"$USER_DATA\",
    \"backups\": \"$BACKUPS\",
    \"enable_ipv6\": true
  }")

# Check for errors
ERROR=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error',''))" 2>/dev/null || echo "parse_error")
if [[ -n "$ERROR" && "$ERROR" != "" ]]; then
  echo "  ERROR: $ERROR"
  exit 1
fi

INSTANCE_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['instance']['id'])")
echo "  Instance ID: $INSTANCE_ID"

# ── Wait for IP ──────────────────────────────────────────────
echo "[3/4] Waiting for instance to be active..."

for i in $(seq 1 60); do
  INST=$(curl -s -H "Authorization: Bearer $VULTR_API_KEY" \
    "https://api.vultr.com/v2/instances/$INSTANCE_ID")

  STATUS=$(echo "$INST" | python3 -c "import json,sys; d=json.load(sys.stdin).get('instance',{}); print(d.get('status',''))")
  IP=$(echo "$INST" | python3 -c "import json,sys; d=json.load(sys.stdin).get('instance',{}); print(d.get('main_ip','0.0.0.0'))")

  if [[ "$STATUS" == "active" && "$IP" != "0.0.0.0" && -n "$IP" ]]; then
    echo "  Active! IP: $IP"
    break
  fi

  printf "  [%d/60] %s / %s\r" "$i" "$STATUS" "$IP"
  sleep 10
done

if [[ "$IP" == "0.0.0.0" || -z "$IP" ]]; then
  echo "  Timed out waiting for IP. Check Vultr dashboard."
  echo "  Instance ID: $INSTANCE_ID"
  exit 1
fi

# ── Update DNS ───────────────────────────────────────────────
echo "[4/4] Updating DNS..."
"$SCRIPT_DIR/update-dns.sh" "$ENV_NAME" "$IP"

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
echo "Provisioning complete!"
echo "═══════════════════════════════════════════════"
echo "  Instance:  $INSTANCE_ID"
echo "  IP:        $IP"
echo "  Domain:    $DOMAIN"
echo "  Admin:     $NSO_ADMIN_EMAIL / $NSO_ADMIN_PASSWORD"
echo ""
echo "Cloud-init is running — services will be ready in ~5-8 min."
echo "Monitor: ssh root@$IP 'tail -f /var/log/cloud-init-output.log'"
