# NSO — Deploy Guide

## 1. Fresh VPS Setup (Central Server)

### From GitHub (no nso.dev needed)

```bash
git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git /opt/nso/repo
cd /opt/nso/repo
bash nso/base/install.sh --central --email admin@nso.dev --password YOUR_ADMIN_PASSWORD
```

### From running nso.dev instance

```bash
curl -fsSL https://nso.dev/install | bash -s -- \
  --central \
  --host https://nso.dev \
  --email admin@nso.dev \
  --password YOUR_ADMIN_PASSWORD
```

**Important**: The `curl` method requires nso.dev to be running. If nso.dev is not up, use the git clone method above.

This installs: Node.js 20, Python 3, nginx, certbot, PostgreSQL 16, UFW, fail2ban, and the NSO agent.

### What `--central` does

- Installs PostgreSQL 16 via official apt repo
- Creates database `nso` with user `nso` and auto-generated password
- Writes `DATABASE_URL=postgresql://nso:{password}@localhost:5432/nso` to `/opt/nso/config/agent.env`
- The central server uses PostgreSQL; user VPS instances use SQLite via the agent

### Agent-only install (user VPS, called by cloud-init)

```bash
# Requires nso.dev to be running (agent code downloaded from there)
curl -fsSL https://nso.dev/install | bash -s -- --host https://nso.dev --token $NSO_TOKEN
```

### Install steps (in order)

1. **System packages**: nginx, certbot, python3, git, curl, ufw, jq, fail2ban
2. **PostgreSQL 16** (`--central` only): creates DB `nso`, user `nso`, writes `DATABASE_URL`
3. **Node.js 20**: ensures >= 18 LTS
4. **User & directories**: creates `nso` system user, `/opt/nso/{data,config,workspaces,venv,vm,repo}`
5. **Python venv**: FastAPI, uvicorn, asyncpg, httpx, pyyaml, websockets
6. **Agent code**: download from `{NSO_HOST}/api/download/agent` OR git clone fallback → copies `vm/agent`, `vm/cli` to `/opt/nso/`
7. **CLI**: creates `/usr/local/bin/nso` symlink
8. **Agent config**: writes `/opt/nso/config/agent.env` with auto-generated `NSO_JWT_SECRET` (64-char hex), `AGENT_ADMIN_PASSWORD`
9. **Nginx config**: reverse proxy `/agent/*` → :8081, `/` → static files
10. **Systemd**: creates `nso-agent.service` (uvicorn as root on 127.0.0.1:8081)
11. **Default workspace**: creates landing page HTML at `/opt/nso/workspaces/default/static/`
12. **Firewall**: enables ufw, opens 22, 80, 443
13. **SSL**: runs certbot if domain auto-detected (reverse DNS lookup)
14. **Start agent**: `systemctl start nso-agent`
15. **Platform registration**: POSTs instance metadata back to NSO_HOST (if NSO_TOKEN provided)

### Bootstrap method

The installer tries two sources for agent code:
1. **HTTP download** from `{NSO_HOST}/api/download/agent` (presigned URL)
2. **Fallback**: `git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git`

If nso.dev is not running, it falls back to GitHub clone automatically.

### Verify installation

```bash
systemctl status nso-agent
curl http://localhost:8081/health
```

---

## 2. PostgreSQL Setup (Existing VPS)

If you already have NSO running with SQLite and want to switch to PostgreSQL:

```bash
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

## 4. Deploy System

The deploy system has three layers: Central Server orchestration, Agent-side execution, and AI-powered Deploy Agent chat.

### Layer 1: Central Server Direct Deploy

**Core function**: `deploy_to_instance(project_id, instance_id, workspace_name, branch, command)`

**Flow**:
1. Check project not frozen (billing status)
2. Check daily deploy limit (from billing plan)
3. Acquire semaphore (`MAX_CONCURRENT_DEPLOYS=3`) to rate-limit server-wide
4. Sync workspace files via rsync (fallback: scp) to `/opt/app` on target
5. Detect stack (package.json, requirements.txt, Dockerfile, etc.)
6. Install deps (npm, pip, cargo, docker-compose) — timeout 300s
7. Set env vars → append to `.env` on remote
8. Create systemd service `nso-app.service`
9. Configure nginx → proxy to localhost:{port} or static serving
10. Setup SSL via Let's Encrypt (via agent)
11. Update instance state to RUNNING
12. Return deploy result with URL

**File sync** (sync.py):
- rsync first (with `-o StrictHostKeyChecking=no`)
- Excludes: `.git`, `node_modules`, `__pycache__`, `.env`, `venv`, `.venv`
- Timeout: 300s; on rsync failure → fallback to sequential scp

**Settings**: `REMOTE_APP_DIR="/opt/app"`, `DEFAULT_PORT=3000`

### Layer 2: Agent-Side Execution (.zar)

Agent receives `.zar` via `POST /deploy/pull` (R2 SigV4 download) or `POST /deploy/upload` (multipart).

**Flow**:
1. Download .zar from R2 (AWS Signature V4 HMAC-SHA256, no boto3)
2. Create snapshot of current state at `{SNAPSHOTS_DIR}/{app}/{timestamp}/`
3. Store nginx + systemd configs in `.nso-service-configs/` subfolder
4. Extract .zar to target directory
5. Detect stack and install deps
6. If `deploy.toml` exists → run 10-phase pipeline (see below)
7. Hand off to supervisor for process lifecycle management
8. Auto-prune old snapshots (keeps max 5 per app)

**Deploy state**: persists to `/opt/nso/data/deploy-state.json` with atomic file locking (fcntl)

**Rollback**: restores filesystem + service configs + reloads nginx/systemd

**Stack detection**:

| Marker | Stack | Install command |
|--------|-------|----------------|
| `package.json` | node | `npm install --production` |
| `requirements.txt` | python | `/opt/nso/venv/bin/pip install -r requirements.txt` |
| `go.mod` | go | `go build ./...` |
| `Cargo.toml` | rust | `cargo build --release` |
| `docker-compose.yml` | docker | `docker compose up -d --build` |
| `index.html` | static | `echo ok` |

### Layer 3: Deploy Agent AI (chat-based deploy)

AI-powered deploy assistant accessible via chat interface. Uses dual-model architecture.

#### Model Configuration

```bash
# Supervisor LLM (tool execution, must support function calling)
DEPLOY_AGENT_API_KEY=...
DEPLOY_AGENT_API_URL=https://api.groq.com/openai/v1
DEPLOY_AGENT_MODEL=openai/gpt-oss-20b
DEPLOY_AGENT_PROVIDER=groq

# Worker LLM (optional, response composition — enables dual-model mode)
DEPLOY_AGENT_WORKER_API_KEY=...
DEPLOY_AGENT_WORKER_MODEL=...
DEPLOY_AGENT_WORKER_API_URL=...

DEPLOY_AGENT_MAX_STEPS=8          # max tool calls per run
DEPLOY_AGENT_MAX_COMPLETION_TOKENS=8192
```

**Dual-model mode** (when WORKER vars set):
1. **Supervisor** receives tools, executes them silently (no chat)
2. **Worker** composes human-friendly response from tool results

**Single-model mode** (fallback): same LLM handles both

#### Deploy Agent Tools

**Workspace tools**: `analyze_project`, `generate_deploy_config`, `list_workspaces`, `list_instances`, `read_workspace_file`, `write_workspace_file`, `delete_workspace_file`, `create_workspace`, `exec_in_workspace`, `list_workspace_files`, `clean_workspace`

**Deploy tools**: `run_build`, `run_ship`, `check_deploy_status`, `run_validation`

**Secrets tools**: `list_secrets`, `add_secret`

**Connector tools**: `setup_connector` (github, s3, slack, cloudflare, r2), `list_connectors`

**Infrastructure tools**: `list_instances`, `create_instance`, `manage_service`, `link_workspace_instance`, `manage_domain`

**Mesh tools**: `list_mesh_devices`, `list_mesh_groups`, `register_mesh_device`, `exec_on_mesh_device`, `exec_on_mesh_group`, `deploy_to_mesh`, `mesh_device_status`, `manage_mesh_group`

#### run_ship flow (the main deploy command)

1. Auto-claim subdomain for user (if not claimed)
2. Resolve deploy target: explicit ID → workspace linked instance → config → first available compute node → first running instance → fail
3. Pack workspace into .zar (tar.gz with manifest + config + files)
4. Push to R2: `{project_id}/{workspace}/{branch}/v{version}.zar`
5. Authenticate to agent at target IP:8081
6. Deploy via agent `/deploy/pull` with R2 credentials + secrets from DB
7. Auto-assign domain: `{workspace}-{user_subdomain}.nso.dev` (Cloudflare DNS)
8. Auto-setup nginx + SSL on agent
9. Send notification to user inbox with deploy URL

**Service mapping for restarts**:
- Platform workspaces: `server` → nso, `agent` → nso-agent, `dashboard/admin/cli` → no restart
- User workspaces: static/custom → no restart, else → nso-app

### Deploy via CLI

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

### Self-update (platform code)

Updates the NSO platform itself (agent, central server, dashboard):

```bash
curl -X POST \
  -H "Authorization: Bearer AGENT_JWT" \
  http://VPS_IP:8081/deploy/self-update
```

Or manually:
```bash
cd /opt/nso/repo && git pull origin main
systemctl restart nso nso-agent
```

### Deploy Flows Summary

**Flow 1: Central Server Direct Deploy**
```
POST /api/projects/{pid}/instances/{iid}/deploy
→ billing check → semaphore → rsync files → detect stack → install deps
→ create systemd service → configure nginx → SSL → state=RUNNING → return URL
```

**Flow 2: Deploy Agent Ship (via Chat)**
```
User: "deploy my-workspace"
Supervisor: run_ship("my-workspace", branch="main")
  → pack .zar → push R2 → agent /deploy/pull → snapshot → extract → restart
  → auto-assign domain: my-workspace-user.nso.dev → nginx + SSL
Worker: "Listo! Tu app está en: https://my-workspace-user.nso.dev"
```

**Flow 3: Mesh Deploy (External Servers)**
```
User: "deploy to all production servers"
Supervisor: deploy_to_mesh("my-workspace", target="grp_prod")
  → pack .zar → SCP to each device → extract → restart on each
Worker: "Desplegado en 3/3 servidores."
```

---

## 5. deploy.toml — Pipeline Configuration

When `deploy.toml` exists in a workspace, the agent runs a 10-phase pipeline instead of simple stack detection.

### Phases

| # | Phase | What it does |
|---|-------|-------------|
| 0 | **Prepare** | Parse deploy.toml, resolve secrets, write .env file |
| 1 | **Pre-hooks** | Execute `hooks.pre_deploy` (on_fail: abort/warn/ignore) |
| 2 | **System** | Install packages, create users, setup firewall, enable services |
| 3 | **Setup** | Create dirs, write files (with `{{KEY}}` template interpolation), run setup scripts |
| 4 | **Install** | Run `[install]` command or auto-detect (npm install, pip install, etc.) |
| 5 | **Build** | Run `[build]` command + additional build steps |
| 6 | **Data** | Run migrations (`[data.migrate]`) and seeds (`[data.seed]` with `only_if: first_deploy`) |
| 7 | **Services** | Generate systemd units from `[services.*]`, install nginx config, request SSL certs |
| 8 | **Health** | Run health checks (HTTP, TCP, custom) with configurable retries |
| 9 | **Post-hooks** | Execute `hooks.post_deploy` and smoke tests |

### Key features

- **Service topological sort**: honors `depends_on` relationships
- **Template interpolation**: replaces `{{KEY}}` with env var values
- **First deploy detection**: `.nso-first-deploy-done` marker file
- **Failure handling**: `on_fail: abort | warn | ignore | rollback`
- **On failure**: restores snapshot, reloads systemd + nginx, runs `on_rollback` hooks
- **After success**: hands process specs to supervisor for lifecycle management

### Full schema

```toml
[workspace]
name = "myapp"
version = "1.0.0"

[system]
packages = ["redis-server", "postgresql-client"]
users = [{name = "appuser", shell = "/bin/bash", groups = ["docker"]}]
services.enable = ["redis-server"]

[setup]
dirs.create = [{path = "/opt/app", owner = "appuser", mode = "0755"}]
files = [{path = "/etc/my.conf", content = "...", template = true}]
scripts = [{name = "init", command = "...", timeout = 60}]

[install]
command = "npm install --production"
timeout = 300

[build]
command = "npm run build"
env = {NODE_ENV = "production"}
steps = [{name = "bundle", command = "..."}]

[data]
migrate.command = "python manage.py migrate"
seed.command = "python manage.py seed"
seed.only_if = "first_deploy"

[services.api]
command = "/opt/app/start.sh"
port = 3000
health_path = "/health"
depends_on = ["db"]
restart_policy = "always"

[services.db]
command = "redis-server"
port = 6379

[nginx]
# nginx config template

[domains]
# [{name = "api.example.com", ssl = true}]

[health]
strategy = "http"   # http | tcp | custom
port = 3000
path = "/health"
timeout = 30
retries = 3

[hooks]
pre_deploy = [{command = "...", on_fail = "abort"}]
post_deploy = [{command = "..."}]
on_rollback = [{command = "..."}]
```

---

## 6. .zar Package System

### Format

A tar.gz archive:
```
.zar-manifest.json   — metadata, version, hash, dependencies
config.toml          — workspace config
files/               — actual workspace files
```

### R2 Storage Layout
```
{project_id}/{workspace}/{branch}/v{version}.zar
{project_id}/{workspace}/{branch}/latest.zar
{project_id}/{workspace}/branches.json
_modules/{name}/v{version}.zar          # System modules
_modules/{name}/latest.zar
```

### Workspace Dependencies

Workspaces depend on others via `[package.dependencies]` in config.toml.
Resolved recursively (max depth 5) from R2.

---

## 7. Process Supervisor

The agent supervisor (vm/agent/supervisor.py) replaces blind systemctl; maintains desired vs actual process state.

### Process states

```
PENDING → STARTING → RUNNING ⇄ UNHEALTHY
                   → RESTARTING → RUNNING
                   → FAILED (max 5 restarts)
                   → UPDATING (rolling update)
                   → DRAINING (graceful shutdown)
                   → STOPPED (intentional)
```

### Reconciliation loop (every 5s)

1. Start missing processes (respecting `depends_on` order)
2. Check alive processes still running
3. Detect version drift → trigger rolling update
4. Reset restart counter after 300s stability window
5. Stop orphaned processes

### Health checking (every 10s)

- Samples CPU, memory from `/proc/PID/status`
- Optional HTTP health check: `GET http://127.0.0.1:{port}{health_path}`
- Marks UNHEALTHY after 3 consecutive failures; recovers to RUNNING when health returns

### Rolling update (blue-green)

1. Start new process on temp port (port + 10000)
2. Wait for health checks to pass
3. Kill old process (drain timeout)
4. Start new on correct port
5. Graceful shutdown: SIGTERM → wait drain_timeout → SIGKILL

### Crash handling

- Exponential backoff: 2^restart_count seconds (capped at 60s)
- If >50% of processes fail → auto-rollback via `/opt/nso/data/rollback-request.json`

### State persistence

Saves to `/opt/nso/data/supervisor-state.json`; restores on agent restart and re-verifies PIDs.

---

## 8. Nginx Configuration

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

    location /ws/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        root /opt/nso/client/dashboard/static;
        try_files $uri $uri/ /index.html;
    }
}
```

SSL is auto-configured via certbot if a domain is set.

---

## 9. Systemd Services

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

## 10. Build Dashboard

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

## 11. Directory Structure on VPS

```
/opt/nso/
├── config/
│   ├── agent.env           # Agent: JWT_SECRET, AGENT_ADMIN_PASSWORD, DATABASE_URL
│   └── nso.env             # Central: DATABASE_URL, provider keys
├── data/
│   ├── nso.db              # SQLite (legacy/agent-only)
│   ├── metrics.db          # SQLite metrics store (boot progress)
│   ├── deploy-state.json   # Current deploy state (fcntl locked)
│   ├── supervisor-state.json # Process supervisor state
│   └── rollback-request.json # Auto-rollback trigger (>50% process failure)
├── workspaces/             # Deployed workspace files
│   └── default/static/     # Default landing page
├── venv/                   # Python virtualenv
├── vm/
│   ├── agent/              # Agent source
│   ├── cli/                # CLI source
│   └── nso                 # CLI binary
├── vms/                    # Pool VM configs (pool_handler.py)
│   └── {vm_id}/config.json
├── domains/                # Per-domain env files (envvars.py scopes)
│   └── {domain}/.env
├── .env                    # General scope env vars
├── client/
│   ├── dashboard/static/   # Built dashboard (served by nginx)
│   └── admin/static/       # Built admin dashboard
└── repo/                   # Git clone of setupo (for updates)
```

---

## 12. Troubleshooting

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

# Check deploy state
cat /opt/nso/data/deploy-state.json | python3 -m json.tool

# Check supervisor state
cat /opt/nso/data/supervisor-state.json | python3 -m json.tool

# Check agent version
curl http://localhost:8081/health | python3 -m json.tool | grep version

# Rollback last deploy
curl -X POST -H "Authorization: Bearer AGENT_JWT" \
  http://localhost:8081/deploy/rollback
```
