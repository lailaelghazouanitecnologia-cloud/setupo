# NSO — Deploy Guide

## 1. Fresh VPS Setup (Central Server)

One-line install on a fresh Debian/Ubuntu VPS:

```bash
curl -fsSL https://nso.dev/install | bash -s -- \
  --central \
  --host https://nso.dev \
  --email admin@nso.dev \
  --password YOUR_ADMIN_PASSWORD
```

This installs: Node.js 20, Python 3, nginx, certbot, PostgreSQL 16, UFW, fail2ban, and the NSO agent.

### What `--central` does

- Installs PostgreSQL 16
- Creates database `nso` with user `nso`
- Writes `DATABASE_URL` to `/opt/nso/config/agent.env`
- The central server uses PostgreSQL; user instances use SQLite via the agent

### Manual install (step by step)

```bash
# 1. Clone repo
git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git /opt/nso/repo

# 2. Run installer
cd /opt/nso/repo
bash nso/base/install.sh --central --email admin@nso.dev --password YOUR_PASS

# 3. Verify
systemctl status nso-agent
curl http://localhost:8081/health
```

---

## 2. PostgreSQL Setup (Existing VPS)

If you already have NSO running with SQLite and want to switch to PostgreSQL:

```bash
# Install PostgreSQL + migrate existing data
bash nso/base/setup-postgres.sh --migrate /opt/nso/data/nso.db
```

Options:
```
--password PASS       DB password (auto-generated if not set)
--migrate PATH        Migrate from existing SQLite database
--skip-install        Skip PostgreSQL install (already have it)
--db-name NAME        Database name (default: nso)
--db-user USER        Database user (default: nso)
```

After running, restart NSO:
```bash
systemctl restart nso
```

### Manual PostgreSQL setup

```bash
# Install
apt install postgresql-16

# Create user + database
sudo -u postgres psql -c "CREATE USER nso WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "CREATE DATABASE nso OWNER nso;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE nso TO nso;"
sudo -u postgres psql -d nso -c "GRANT ALL ON SCHEMA public TO nso;"

# Add to env
echo "DATABASE_URL=postgresql://nso:your_password@localhost:5432/nso" >> /opt/nso/config/nso.env

# Restart
systemctl restart nso
```

---

## 3. Data Migration (SQLite → PostgreSQL)

```bash
python3 nso/base/migrate-sqlite-to-pg.py \
  --sqlite /opt/nso/data/nso.db \
  --pg postgresql://nso:your_password@localhost:5432/nso
```

Options:
```
--dry-run           Preview without writing
--tables t1,t2      Only migrate specific tables
--skip t1,t2        Skip specific tables
--batch-size 500    Rows per INSERT batch
```

The migration is idempotent (ON CONFLICT DO NOTHING) — safe to re-run.

---

## 4. Deploy Code to VPS

### Via .zar (recommended)

```bash
# From CLI
nso login --host https://nso.dev
nso ship my-workspace inst_xxx

# Or via API
curl -X POST \
  -H "Authorization: Bearer sk_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"inst_xxx"}' \
  https://nso.dev/api/projects/{pid}/zar/{name}/ship
```

The `/ship` endpoint does: pack → push to R2 → agent pulls → snapshot → extract → restart.

### Via self-update (platform code)

Updates the NSO platform itself (agent, central server, dashboard):

```bash
curl -X POST \
  -H "Authorization: Bearer AGENT_JWT" \
  http://VPS_IP:8081/deploy/self-update
```

Or from the agent on the VPS:
```bash
cd /opt/nso/repo && git pull origin main
systemctl restart nso nso-agent
```

---

## 5. Nginx Configuration

The installer creates `/etc/nginx/sites-available/nso`:

```nginx
server {
    listen 80 default_server;
    server_name YOUR_DOMAIN;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
    }

    location /agent/ {
        proxy_pass http://127.0.0.1:8081/;
    }

    location / {
        root /opt/nso/client/dashboard/static;
        try_files $uri $uri/ /index.html;
    }
}
```

SSL is auto-configured via certbot if a domain is set.

---

## 6. Systemd Services

```bash
# Central server
systemctl status nso
systemctl restart nso
journalctl -u nso -f

# Agent
systemctl status nso-agent
systemctl restart nso-agent
journalctl -u nso-agent -f
```

Service files:
- `/etc/systemd/system/nso.service` — central server (uvicorn :8000)
- `/etc/systemd/system/nso-agent.service` — agent (uvicorn :8081)

---

## 7. Build Dashboard

```bash
cd /opt/nso/client/dashboard
npm install
npm run build
npm run export    # generates static/ for nginx
```

Admin dashboard:
```bash
cd /opt/nso/client/admin
npm install
npm run build
npm run export
```

---

## 8. Directory Structure on VPS

```
/opt/nso/
├── config/
│   ├── agent.env       # Agent config (JWT_SECRET, passwords, DATABASE_URL)
│   └── nso.env         # Central server config
├── data/
│   └── nso.db          # SQLite database (legacy, or agent-only)
├── workspaces/         # Deployed workspace files
├── venv/               # Python virtualenv
├── vm/
│   ├── agent/          # Agent code
│   └── cli/            # CLI code
├── client/
│   ├── dashboard/      # Main dashboard
│   └── admin/          # Admin dashboard
└── repo/               # Git clone of setupo
```

---

## 9. Troubleshooting

```bash
# Check services
systemctl status nso nso-agent nginx postgresql

# Check logs
journalctl -u nso -n 50
journalctl -u nso-agent -n 50

# Check ports
ss -tlnp | grep -E '8000|8081|5432|80|443'

# Test agent health
curl http://localhost:8081/health

# Test central server
curl http://localhost:8000/api/health

# Test database
sudo -u postgres psql -d nso -c "SELECT COUNT(*) FROM users;"

# Check nginx config
nginx -t

# Check firewall
ufw status
```
