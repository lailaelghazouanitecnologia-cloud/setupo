#!/bin/bash
# Capsule: python-app - Setup Python application environment
set -euo pipefail

apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv

mkdir -p /opt/app
python3 -m venv /opt/app/venv

# If requirements.txt exists in capsule data, install them
if [ -f /opt/capsules/python-app/requirements.txt ]; then
    /opt/app/venv/bin/pip install -r /opt/capsules/python-app/requirements.txt
fi

echo "python-app capsule installed"
