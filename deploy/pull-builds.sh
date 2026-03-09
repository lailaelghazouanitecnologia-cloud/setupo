#!/bin/bash
# pull-builds.sh — Download prebuilt dashboards from R2
# Usage: ./pull-builds.sh [R2_ENDPOINT] [R2_ACCESS_KEY_ID] [R2_SECRET_ACCESS_KEY] [R2_BUCKET]
#
# Downloads precompiled dashboard and admin builds from R2 instead of
# running npm/bun build on the VPS. This saves ~5-10 minutes on deploy.
#
# Requires: python3 (for S3v4 signing), curl

set -euo pipefail

R2_ENDPOINT="${1:-${R2_ENDPOINT:-}}"
R2_ACCESS_KEY_ID="${2:-${R2_ACCESS_KEY_ID:-}}"
R2_SECRET_ACCESS_KEY="${3:-${R2_SECRET_ACCESS_KEY:-}}"
R2_BUCKET="${4:-${R2_BUCKET:-nso}}"

DASHBOARD_DIR="${DASHBOARD_DIR:-/opt/nso/client/dashboard}"
ADMIN_DIR="${ADMIN_DIR:-/opt/nso/client/admin}"

if [ -z "$R2_ENDPOINT" ] || [ -z "$R2_ACCESS_KEY_ID" ] || [ -z "$R2_SECRET_ACCESS_KEY" ]; then
  echo "ERROR: R2 credentials required (env vars or arguments)"
  exit 1
fi

download_from_r2() {
  local r2_key="$1"
  local output_file="$2"

  python3 -c "
import hashlib, hmac, datetime, sys, urllib.request, ssl

endpoint = '${R2_ENDPOINT}'
access_key = '${R2_ACCESS_KEY_ID}'
secret_key = '${R2_SECRET_ACCESS_KEY}'
bucket = '${R2_BUCKET}'
key = '${r2_key}'
output = '${output_file}'

now = datetime.datetime.now(datetime.timezone.utc)
datestamp = now.strftime('%Y%m%d')
amzdate = now.strftime('%Y%m%dT%H%M%SZ')
host = endpoint.replace('https://','')
payload_hash = 'UNSIGNED-PAYLOAD'

headers = {'host': host, 'x-amz-date': amzdate, 'x-amz-content-sha256': payload_hash}
signed_headers = ';'.join(sorted(headers))
canonical_headers = ''.join(f'{k}:{headers[k]}\n' for k in sorted(headers))
canonical_request = f'GET\n/{bucket}/{key}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}'

scope = f'{datestamp}/auto/s3/aws4_request'
sts = f'AWS4-HMAC-SHA256\n{amzdate}\n{scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}'

def sign(k, m):
    return hmac.new(k, m.encode(), hashlib.sha256).digest()
k = sign(f'AWS4{secret_key}'.encode(), datestamp)
k = sign(k, 'auto')
k = sign(k, 's3')
k = sign(k, 'aws4_request')
sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()

auth = f'AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed_headers}, Signature={sig}'
url = f'{endpoint}/{bucket}/{key}'

req = urllib.request.Request(url, headers={
    'Host': host,
    'x-amz-date': amzdate,
    'x-amz-content-sha256': payload_hash,
    'Authorization': auth,
})
ctx = ssl.create_default_context()
with urllib.request.urlopen(req, context=ctx) as resp:
    with open(output, 'wb') as f:
        f.write(resp.read())
    print(f'Downloaded {key} ({resp.length or \"?\"} bytes)')
"
}

echo "=== Pulling prebuilt dashboards from R2 ==="

# Dashboard
echo "Downloading dashboard build..."
mkdir -p "$DASHBOARD_DIR"
download_from_r2 "_builds/dashboard/latest.tar.gz" "/tmp/dashboard-build.tar.gz"
tar xzf /tmp/dashboard-build.tar.gz -C "$DASHBOARD_DIR"
rm -f /tmp/dashboard-build.tar.gz
echo "Dashboard extracted to $DASHBOARD_DIR"

# Admin
echo "Downloading admin build..."
mkdir -p "$ADMIN_DIR"
download_from_r2 "_builds/admin/latest.tar.gz" "/tmp/admin-build.tar.gz"
tar xzf /tmp/admin-build.tar.gz -C "$ADMIN_DIR"
rm -f /tmp/admin-build.tar.gz
echo "Admin extracted to $ADMIN_DIR"

echo "=== Builds pulled successfully ==="
