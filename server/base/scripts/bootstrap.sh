#!/bin/bash
# NSO — Post-boot bootstrap script (runs via SSH after VPS is ready)
set -euo pipefail

echo "=== NSO bootstrap starting ==="

# Wait for cloud-init to finish
cloud-init status --wait 2>/dev/null || true

# Verify basics
echo "Node: $(node --version 2>/dev/null || echo 'not installed')"
echo "Python: $(python3 --version 2>/dev/null || echo 'not installed')"
echo "Git: $(git --version 2>/dev/null || echo 'not installed')"
echo "Nginx: $(nginx -v 2>&1 || echo 'not installed')"

# Ensure app dir
mkdir -p /opt/app

echo "=== NSO bootstrap complete ==="
