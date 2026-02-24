#!/bin/bash
# Setupo — Deploy script (runs on the instance to start the app)
set -euo pipefail

APP_DIR="${1:-/opt/app}"
echo "=== Deploying from $APP_DIR ==="
cd "$APP_DIR"

# Detect and install
if [ -f package.json ]; then
    echo "Node.js project detected"
    npm install --production

    # Create systemd service
    cat > /etc/systemd/system/setupo-app.service <<EOF
[Unit]
Description=Setupo App
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/npm start
Restart=on-failure
RestartSec=5
Environment=NODE_ENV=production
Environment=PORT=3000

[Install]
WantedBy=multi-user.target
EOF

elif [ -f requirements.txt ]; then
    echo "Python project detected"
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt

    ENTRYPOINT="main.py"
    [ -f app.py ] && ENTRYPOINT="app.py"
    [ -f manage.py ] && ENTRYPOINT="manage.py runserver 0.0.0.0:3000"

    cat > /etc/systemd/system/setupo-app.service <<EOF
[Unit]
Description=Setupo App
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $ENTRYPOINT
Restart=on-failure
RestartSec=5
Environment=PORT=3000

[Install]
WantedBy=multi-user.target
EOF

elif [ -f docker-compose.yml ] || [ -f docker-compose.yaml ]; then
    echo "Docker Compose project detected"
    docker compose up -d --build
    echo "=== Deploy complete (Docker) ==="
    exit 0

elif [ -f index.html ]; then
    echo "Static site detected — copying to nginx root"
    cp -r . /var/www/html/
    systemctl restart nginx
    echo "=== Deploy complete (static) ==="
    exit 0

else
    echo "Unknown project type"
    exit 1
fi

# Start service
systemctl daemon-reload
systemctl enable setupo-app
systemctl restart setupo-app
echo "=== Deploy complete ==="
