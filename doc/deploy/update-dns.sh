#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# NSO — Update Cloudflare DNS records for an environment
#
# Usage:
#   ./update-dns.sh <env> <ip>
#   ./update-dns.sh prod 208.85.16.21
#   ./update-dns.sh test 1.2.3.4
#
# Requires: CF_API_TOKEN, CF_NSO_ZONE_ID
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENVS_FILE="$SCRIPT_DIR/environments.json"

ENV_NAME="${1:-}"
NEW_IP="${2:-}"

if [[ -z "$ENV_NAME" || -z "$NEW_IP" ]]; then
  echo "Usage: $0 <env> <ip>"
  echo "  env: prod | test"
  echo "  ip:  new IPv4 address"
  exit 1
fi

for var in CF_API_TOKEN CF_NSO_ZONE_ID; do
  if [[ -z "${!var:-}" ]]; then
    echo "Error: $var is not set"
    exit 1
  fi
done

# Load DNS record names from environment config
DNS_ROOT=$(python3 -c "
import json, sys
envs = json.load(open('$ENVS_FILE'))
if '$ENV_NAME' not in envs:
    print(f'Error: unknown env \"$ENV_NAME\"', file=sys.stderr)
    sys.exit(1)
print(envs['$ENV_NAME']['dns_records']['root'])
")

DNS_WILDCARD=$(python3 -c "
import json
envs = json.load(open('$ENVS_FILE'))
print(envs['$ENV_NAME']['dns_records']['wildcard'])
")

echo "Updating DNS for $ENV_NAME:"
echo "  $DNS_ROOT     → $NEW_IP"
echo "  $DNS_WILDCARD → $NEW_IP"

# ── Helper: find or create A record ─────────────────────────
update_or_create_record() {
  local name="$1"
  local ip="$2"

  # Search for existing record
  local record_id
  record_id=$(curl -s \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    "https://api.cloudflare.com/client/v4/zones/$CF_NSO_ZONE_ID/dns_records?type=A&name=$name" \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('result', [])
print(results[0]['id'] if results else '')
")

  if [[ -n "$record_id" ]]; then
    # Update existing
    local resp
    resp=$(curl -s -X PATCH \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -H "Content-Type: application/json" \
      "https://api.cloudflare.com/client/v4/zones/$CF_NSO_ZONE_ID/dns_records/$record_id" \
      -d "{\"content\": \"$ip\"}")
    local ok
    ok=$(echo "$resp" | python3 -c "import json,sys; print(json.load(sys.stdin).get('success', False))")
    if [[ "$ok" == "True" ]]; then
      echo "  Updated $name (record $record_id)"
    else
      echo "  FAILED to update $name: $resp"
      return 1
    fi
  else
    # Create new
    local resp
    resp=$(curl -s -X POST \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -H "Content-Type: application/json" \
      "https://api.cloudflare.com/client/v4/zones/$CF_NSO_ZONE_ID/dns_records" \
      -d "{\"type\": \"A\", \"name\": \"$name\", \"content\": \"$ip\", \"ttl\": 300, \"proxied\": false}")
    local ok
    ok=$(echo "$resp" | python3 -c "import json,sys; print(json.load(sys.stdin).get('success', False))")
    if [[ "$ok" == "True" ]]; then
      local new_id
      new_id=$(echo "$resp" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['id'])")
      echo "  Created $name (record $new_id)"
    else
      echo "  FAILED to create $name: $resp"
      return 1
    fi
  fi
}

# ── Update both records ──────────────────────────────────────
update_or_create_record "$DNS_ROOT" "$NEW_IP"
update_or_create_record "$DNS_WILDCARD" "$NEW_IP"

echo ""
echo "DNS updated. Propagation: ~1 min (TTL 300s)."
