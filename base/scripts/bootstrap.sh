#!/bin/bash
# MMS — Post-boot bootstrap script (runs via SSH after VPS is ready)
set -euo pipefail

echo "=== MMS bootstrap starting ==="

# Wait for cloud-init to finish
cloud-init status --wait 2>/dev/null || true

# Verify basics
echo "Node: $(node --version 2>/dev/null || echo 'not installed')"
echo "Python: $(python3 --version 2>/dev/null || echo 'not installed')"
echo "Git: $(git --version 2>/dev/null || echo 'not installed')"
echo "Nginx: $(nginx -v 2>&1 || echo 'not installed')"

# Ensure app dir
mkdir -p /opt/app

# Check MMS services
echo "MMS API: $(systemctl is-active mms 2>/dev/null || echo 'not running')"
echo "MMS Metrics: $(systemctl is-active mms-metrics 2>/dev/null || echo 'not running')"

echo "=== MMS bootstrap complete ==="
