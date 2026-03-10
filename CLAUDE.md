# NSO — AI Agent Infrastructure Platform

## Infrastructure

| Detail | Value |
|--------|-------|
| Main VPS | 65.20.102.242 (nso.dev) |
| Test VPS | 65.20.103.88 |
| Provider | Vultr (VPS) + Cloudflare (DNS + R2) |
| Repo | github.com/lailaelghazouanitecnologia-cloud/setupo |
| Database | PostgreSQL 16 (central server) / SQLite (agent per VPS) |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              nso/ — CENTRAL SERVER (:8000)                       │
│                                                                 │
│  nso/                              nso/shared/                  │
│  ├── main.py (auto-discovery)      ├── db.py (PostgreSQL+CRUD) │
│  ├── config.py (env vars)          ├── models.py (Pydantic)    │
│  └── config.toml                   ├── errors.py               │
│                                    ├── deps.py (auth deps)     │
│  nso/shared/auth/                  └── ratelimit.py            │
│  ├── jwt.py (JWT+PBKDF2)                                       │
│  ├── keys.py (sk_live_ gen)       nso/engine/ (15 modules)     │
│  └── resolve.py (token→ctx)       ├── auth/     (users, email) │
│                                    ├── billing/  (plans, subs)  │
│  Each engine module has:           ├── compute/  (instances)    │
│  ├── config.toml (discovery)       ├── deploy/   (pipeline)    │
│  ├── routes.py                     ├── storage/  (R2, .zar)    │
│  ├── service.py                    ├── workspace/(config)      │
│  ├── migrations.py                 ├── projects/ (CRUD)        │
│  └── models.py (optional)          ├── dns/      (domains)     │
│                                    ├── addons/   (plugins)     │
│  Cloudflare R2                     ├── admin/    (analytics)   │
│  ├── .zar packages                 ├── notifications/          │
│  ├── branches.json                 ├── orchestrator/ (+LB)     │
│  └── latest.zar per branch         └── secrets/ (env vars)     │
└───────────────────────┬─────────────────────────────────────────┘
                        │  HTTP (no SSH)
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                vm/agent/ — NSO AGENT (per VPS :8081)             │
│                                                                 │
│  ├── main.py       (entry, router mounting, lifespan)           │
│  ├── auth.py       (JWT login, PBKDF2 100k iter)                │
│  ├── files.py      (browse/read/write/delete, sandboxed)        │
│  ├── exec.py       (command execution, blacklist-filtered)      │
│  ├── deploy.py     (pull .zar, snapshot, rollback, self-update) │
│  ├── pipeline.py   (10-phase deploy pipeline via deploy.toml)   │
│  ├── supervisor.py (process lifecycle, health checks, rollback) │
│  ├── pool_handler.py (multi-tenant VM provisioning, Docker/cgroup)│
│  ├── ai.py         (AI model execution proxy)                   │
│  ├── envvars.py    (env var CRUD, scopes, bucket grouping)      │
│  ├── store.py      (SQLite metrics for instance tracking)       │
│  └── models.py     (Pydantic models, Stage enum)                │
│                                                                 │
│  nginx → /api/ (:8000) + /agent/ (:8081) + / (static dashboard)│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  client/dashboard/  — Main Next.js dashboard                    │
│  client/admin/      — Admin Next.js dashboard                   │
│  vm/cli/            — Python CLI (nso login, ship, exec, inst)  │
└─────────────────────────────────────────────────────────────────┘
```

## Authentication

Four auth mechanisms:

| Type | Format | Scope | How to get |
|------|--------|-------|-----------|
| Admin token | random 64 chars (file-backed) | Full platform access | `POST /api/auth/login` (admin creds) |
| User JWT | `usr_header.payload.sig` (HS256) | User-scoped access | `POST /api/auth/login` or `/register` |
| Project API key | `sk_live_xxxx` (SHA256 in DB) | Single project | Created with project, rotatable |
| Agent JWT | `header.payload.sig` (HS256) | Agent endpoints on VPS | `POST /agent/auth/login` |

### Login flow (dashboard)

```
Browser → POST /api/auth/login  → admin token OR user JWT → localStorage["nso_api_token"]
       → POST /agent/auth/login → agent JWT → localStorage["nso_token"]  (admin only)
```

The dashboard uses **two tokens simultaneously**:
- `nso_token` → agent calls (files, exec, secrets, deploy)
- `nso_api_token` → central API calls (projects, workspaces, instances, billing, etc.)

### Dependency injection (nso/shared/deps.py)

```python
require_project  → API key provides project_id; admin gets it from URL
require_admin    → Admin token or user with role="admin"
require_user     → User JWT (any authenticated user)
```

### Token resolution (nso/shared/auth/resolve.py)

```
Token starts with "usr_"  → decode user JWT → AuthContext(user_id, email, role)
Token matches admin file  → AuthContext(is_admin=True)
Token starts with "sk_"   → SHA256 lookup → AuthContext(project_id)
```

## Middleware Stack

```python
RateLimitMiddleware   # Sliding window per IP on auth endpoints
AdminHostMiddleware   # Restrict /api/admin/* to sonfazt.nso.dev
CORSMiddleware        # Standard CORS
```

## Nginx Routing

```
Client (HTTPS :443 → nso.dev)
    ├── /api/*      → proxy_pass 127.0.0.1:8000  (FastAPI central)
    ├── /agent/*    → proxy_pass 127.0.0.1:8081/ (nso-agent)
    ├── /ws/*       → WebSocket proxy :8000
    └── /           → /opt/nso/client/dashboard/static (Next.js export)
```

---

## Install System (nso/base/install.sh)

### Bootstrap method

The installer tries two sources for agent code:
1. **HTTP download** from `{NSO_HOST}/api/download/agent` (presigned URL)
2. **Fallback**: `git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git`

If nso.dev is not running, it falls back to GitHub clone automatically.

### Installation steps (in order)

1. System packages: nginx, certbot, python3, git, curl, ufw, jq, fail2ban
2. PostgreSQL 16 (**--central only**): creates DB `nso`, user `nso`, writes `DATABASE_URL`
3. Node.js 20 (ensures >= 18 LTS)
4. User & directories: creates `nso` system user, `/opt/nso/{data,config,workspaces,venv,vm,repo}`
5. Python venv: FastAPI, uvicorn, asyncpg, httpx, pyyaml, websockets
6. Agent code: download or git clone → copies `vm/agent`, `vm/cli` to `/opt/nso/`
7. CLI: creates `/usr/local/bin/nso` symlink
8. Agent config: writes `/opt/nso/config/agent.env` with auto-generated JWT_SECRET (64-char hex), AGENT_ADMIN_PASSWORD
9. Nginx config: reverse proxy `/agent/*` → :8081, `/` → static files
10. Systemd: creates `nso-agent.service` (uvicorn as root on 127.0.0.1:8081)
11. Default workspace: creates landing page HTML at `/opt/nso/workspaces/default/static/`
12. Firewall: enables ufw, opens 22, 80, 443
13. SSL: runs certbot if domain auto-detected (reverse DNS lookup)
14. Start agent: `systemctl start nso-agent`
15. Platform registration: POSTs instance metadata back to NSO_HOST (if NSO_TOKEN provided)

### What --central does

- Installs PostgreSQL 16 via official apt repo
- Creates database `nso` with user `nso` and auto-generated password
- Writes `DATABASE_URL=postgresql://nso:{password}@localhost:5432/nso` to agent.env
- Central server uses PostgreSQL; user VPS instances use SQLite via the agent

### Usage

```bash
# From GitHub (no nso.dev needed)
git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git
cd setupo && bash nso/base/install.sh --central --email admin@nso.dev

# From running nso.dev instance
curl -fsSL https://nso.dev/install | bash -s -- --central --email admin@nso.dev

# Agent-only (user VPS, called by cloud-init during instance provisioning)
curl -fsSL https://nso.dev/install | bash -s -- --host https://nso.dev --token $NSO_TOKEN
```

---

## NSO Agent — Detailed Reference (vm/agent/)

The agent is a FastAPI app (v0.3.0) running on each VPS at :8081. It handles deployments, file management, process supervision, and monitoring.

### main.py — Entry Point

- **Lifespan**: on startup initializes metrics store, restores VMs, starts supervisor; on shutdown drains processes and closes store
- **CORS**: allows `https://nso.dev`, `https://sonfazt.nso.dev`, `http://localhost:3000`
- **Routers mounted**: files, exec, deploy, secrets, ai, metrics, pool handlers
- **Health endpoint** (`GET /health`): reads `/proc/meminfo`, `/proc/loadavg`, `/proc/uptime` for system metrics; reports agent version, uptime, supervisor status

### auth.py — Agent Authentication

- Single admin user per agent (always `admin@nso.dev`)
- Password: `AGENT_ADMIN_PASSWORD` env var (64-char hex, auto-generated by installer)
- PBKDF2 with **100,000 iterations** (NIST recommendation)
- JWT: HS256, 7-day expiry, signed with `NSO_JWT_SECRET`
- `require_admin` dependency: validates Bearer token from Authorization header

### files.py — Sandboxed File Operations

**Allowed roots**: `/opt/nso`, `/opt/app`, `/var/log/nso`, `/tmp`

**Read-only paths**: `/opt/nso/data/mesh`, `/opt/nso/config`

**Blocked basenames** (never readable/writable): `master_key`, `.env`, `credentials.json`, `service-account.json`

**Security**:
- Path validation: resolves symlinks, checks against ALLOWED_ROOTS
- Symlink checking: verifies real path after resolution
- Max 5MB for reads
- Tree endpoint skips `.git`, `node_modules`, `__pycache__`; depth 1-5

### exec.py — Command Execution

**Blacklist** (rejected patterns):
- Destructive: `rm -rf /`, `mkfs`, `dd`, `/dev/sd*`
- System control: `shutdown`, `reboot`, `poweroff`, `halt`, `init 0/6`
- Fork bombs, `kill -9 -1`
- Reads of: `master_key`, JWT_SECRET, AGENT_ADMIN_PASSWORD

**Limits**:
- Command length: max 4096 chars
- Timeout: 1-300s (default 60s)
- Working directory: must be in `/opt/nso`, `/opt/app`, `/tmp`
- Blocks env injection: `LD_PRELOAD`, `LD_LIBRARY_PATH`, `PYTHONPATH`, `NODE_PATH`

**Service management** (`POST /exec/service`):
- Allowed services: `nso`, `nso-agent`, `nginx`
- Actions: start, stop, restart, status, enable, disable

### deploy.py — Deploy & Snapshot Engine

**R2 download**: AWS Signature V4 HMAC-SHA256 signing (no boto3). Falls back to presigned URLs.

**Snapshot system**:
- Creates snapshot at `{SNAPSHOTS_DIR}/{app}/{timestamp}/` via recursive copytree
- Stores nginx + systemd configs in `.nso-service-configs/` subfolder
- Keeps max 5 snapshots per app (auto-prunes oldest)
- Rollback restores filesystem + service configs + reloads nginx/systemd

**Stack detection** (auto-detect by marker file):

| Marker | Stack | Install command |
|--------|-------|----------------|
| `package.json` | node | `npm install --production` |
| `requirements.txt` | python | `/opt/nso/venv/bin/pip install -r requirements.txt` |
| `go.mod` | go | `go build ./...` |
| `Cargo.toml` | rust | `cargo build --release` |
| `docker-compose.yml` | docker | `docker compose up -d --build` |
| `index.html` | static | `echo ok` |

**Deploy state**: persists to `/opt/nso/data/deploy-state.json` with atomic file locking (fcntl)

**Key endpoints**:
- `POST /deploy/pull` — Download .zar via R2, extract, run pipeline if deploy.toml exists
- `POST /deploy/upload` — Accept multipart .zar, extract, install deps
- `POST /deploy/rollback` — Restore snapshot, reload services
- `GET /deploy/current` — All deployed versions and snapshots
- `POST /deploy/self-update` — Update agent/core/frontend
- `POST /deploy/setup-domain` — Generate nginx config + SSL cert for domain
- `GET /deploy/progress` — Poll for SSE progress during active deploys
- `POST /platform-update` — Pull latest code from repo, rebuild dashboards, restart services

### pipeline.py — 10-Phase Deploy Pipeline (deploy.toml)

Activated when `deploy.toml` exists in workspace and `use_pipeline=true`.

**Phases** (in order):

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

**deploy.toml schema**:
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

**Key features**:
- Service topological sort: honors `depends_on` relationships
- Template interpolation: replaces `{{KEY}}` with env var values
- First deploy detection: `.nso-first-deploy-done` marker file
- Failure handling: `on_fail: abort | warn | ignore | rollback`
- On failure: restores snapshot, reloads systemd + nginx, runs `on_rollback` hooks
- After success: hands process specs to supervisor for lifecycle management

### supervisor.py — Process Lifecycle Manager

Replaces blind systemctl; maintains desired vs actual process state with reconciliation.

**Process states**:
```
PENDING → STARTING → RUNNING ⇄ UNHEALTHY
                   → RESTARTING → RUNNING
                   → FAILED (max 5 restarts)
                   → UPDATING (rolling update)
                   → DRAINING (graceful shutdown)
                   → STOPPED (intentional)
```

**Reconciliation loop** (every 5s):
1. Start missing processes (respecting `depends_on` order)
2. Check alive processes still running
3. Detect version drift → trigger rolling update
4. Reset restart counter after 300s stability window
5. Stop orphaned processes

**Health checking** (every 10s):
- Samples CPU, memory from `/proc/PID/status`
- Optional HTTP health check: `GET http://127.0.0.1:{port}{health_path}`
- Marks UNHEALTHY after 3 consecutive failures; recovers to RUNNING when health returns

**Rolling update** (blue-green):
1. Start new process on temp port (port + 10000)
2. Wait for health checks to pass
3. Kill old process (drain timeout)
4. Start new on correct port
5. Graceful shutdown: SIGTERM → wait drain_timeout → SIGKILL

**Crash handling**:
- Exponential backoff: 2^restart_count seconds (capped at 60s)
- If >50% of processes fail → auto-rollback via `/opt/nso/data/rollback-request.json`

**State persistence**: saves to `/opt/nso/data/supervisor-state.json`; restores on agent restart and re-verifies PIDs

### pool_handler.py — Multi-Tenant VM Provisioning

Host-side endpoints for creating/destroying isolated VMs for build pools or user workloads.

**Security model**:
- Input validation: strict regex `^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$` for vm_id/project_id
- Resource limits: max 16 vCPU, 32GB RAM, 500GB disk
- Auth: JWT OR `NSO_POOL_AGENT_TOKEN` (for pool reconciler)

**Docker backend** (preferred, hardened):
- cap-drop ALL, no-new-privileges, default seccomp
- Read-only root filesystem + tmpfs for /tmp, /run
- Memory swap disabled, PID limit 256 (fork bomb protection)
- User namespace: runs as UID 1000:1000
- Dedicated isolated Docker network per VM

**Cgroup sandbox backend** (fallback, full namespace isolation):
- `unshare`: --pid, --net, --mount, --ipc, --uts, --fork
- Cgroup limits: cpu.max, memory.max, memory.swap.max=0, pids.max=256
- Isolated rootfs with minimal dirs

**Firewall** (iptables per VM):
- Dedicated chain `NSO-VM-{vm_id}`
- Only allows TCP to assigned port range
- Blocks VM-to-VM lateral movement (10.0.0.0/24)
- Allows established connections

**Endpoints**:
- `POST /pool/vms` — Create VM (Docker or cgroup)
- `GET /pool/vms` — List all VMs
- `GET /pool/vms/{vm_id}` — Get VM status
- `DELETE /pool/vms/{vm_id}` — Destroy VM + cleanup firewall

**IP assignment**: `10.0.0.{hash(vm_id) % 254 + 1}/24`

**Config persistence**: `/opt/nso/vms/{vm_id}/config.json`; restored on agent restart

### ai.py — AI App Execution Proxy

Receives AI app run requests from central server, executes locally.

**Endpoint**: `POST /ai/run`

**Flow**:
1. Build payload from inputs + memory context + system prompt
2. Call external AI model (Baseten or custom URL)
3. Detect and store base64-encoded files in output
4. Return results + stored file paths

**Asset storage**: files saved to `/opt/app/assets/{app_slug}/{run_id}/{filename}`. Detects data URIs and raw base64.

**Context injection**: enriches system prompt with project context (workspaces, instances, domains, recent runs)

### envvars.py — Secret Management with Scopes

**Scopes**:
- `general` → `/opt/nso/.env`
- `domain:{name}` → `/opt/nso/domains/{name}/.env`

**Bucket classification** (auto-groups by prefix):
- **auth**: `NSO_ADMIN_*`, `AGENT_ADMIN_*`, `JWT_*`, `SECRET_*`
- **providers**: `VULTR_*`, `CF_*`
- **storage**: `R2_*`
- **system**: `HOST*`, `PORT*`, `DB_*`, `LOG_*`, `CORS_*`, `NSO_*`
- **custom**: everything else

**Key validation**: `^[A-Z][A-Z0-9_]*$` (uppercase, digits, underscores only)

**Endpoints**:
- `GET /secrets/scopes` — List all scopes
- `POST /secrets/scopes` — Create domain scope
- `DELETE /secrets/scopes/{domain}` — Delete scope
- `GET /secrets?scope=` — List secrets grouped by bucket
- `POST /secrets?scope=` — Add secret
- `PUT /secrets/{key}?scope=` — Update secret
- `DELETE /secrets/{key}?scope=` — Delete secret

### store.py — Instance Boot Metrics

SQLite at `/opt/nso/data/metrics.db`. Tracks VPS instance boot/setup progress.

**Stages** (10 total):

| # | Stage | Progress |
|---|-------|----------|
| 1 | BOOTING | 0% |
| 2 | FIREWALL | 5% |
| 3 | PACKAGES | 15% |
| 4 | CLONE_REPO | 35% |
| 5 | PYTHON_SETUP | 55% |
| 6 | NGINX_SETUP | 70% |
| 7 | DATA_DIRS | 80% |
| 8 | SERVICE_START | 90% |
| 9 | HEALTH_CHECK | 95% |
| 10 | READY / ERROR | 100% |

**Key functions**: `register_instance()`, `report(MetricReport)`, `get_metrics()`, `verify_token()`, `delete_metrics()`

---

## Deploy System — Complete Reference

The deploy system has three layers: Central Server orchestration, Agent-side execution, and AI-powered Deploy Agent chat.

### Layer 1: Central Server Deploy (nso/engine/deploy/)

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

### Layer 2: Agent-Side Execution (vm/agent/deploy.py + pipeline.py)

Documented above in Agent section. Summary:
- Agent receives `.zar` via `POST /deploy/pull` (R2 SigV4 download) or `POST /deploy/upload` (multipart)
- Creates snapshot of current state (max 5 kept)
- Extracts .zar, detects stack, installs deps
- If `deploy.toml` exists → runs 10-phase pipeline (pipeline.py)
- Hands off to supervisor for process lifecycle management
- Supports rollback, self-update, domain setup

### Layer 3: Deploy Agent AI (nso/engine/deploy_agent/)

AI-powered deploy assistant accessible via chat interface. Uses dual-model architecture with tool calling.

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

#### Chat API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/.../deploy-agent/threads` | Create deploy thread |
| GET | `/api/.../deploy-agent/threads` | List threads for project |
| GET | `/api/.../deploy-agent/threads/{id}` | Get thread + history |
| PATCH | `/api/.../deploy-agent/threads/{id}` | Update title/workspace |
| DELETE | `/api/.../deploy-agent/threads/{id}` | Delete thread |
| POST | `/api/.../deploy-agent/threads/{id}/stream` | Send message, stream SSE response |

#### Deploy Agent Tool Registry

**Workspace tools** (tools/workspace.py):

| Tool | Purpose |
|------|---------|
| `analyze_project(workspace)` | Detect stack, deps, entry points |
| `generate_deploy_config(workspace)` | Create deploy.toml from analysis |
| `list_workspaces()` | List workspaces (filtered by agent_visible) |
| `list_instances()` | List VPS instances with state/IP/plan |
| `read_workspace_file(workspace, path)` | Read file (blocks sensitive: .env, credentials.json) |
| `write_workspace_file(workspace, path, content)` | Write file (respects readonly/protected) |
| `delete_workspace_file(workspace, path)` | Delete file/dir |
| `create_workspace(name, stack, description, git_url)` | Create workspace, optionally clone from Git |
| `exec_in_workspace(workspace, command, timeout=120)` | Run command (whitelisted: npm, pip, git, make, etc.) |
| `list_workspace_files(workspace, path)` | List directory contents |
| `clean_workspace(workspace, keep)` | Delete all files except specified |

**Deploy tools** (tools/deploy.py):

| Tool | Purpose |
|------|---------|
| `run_build(workspace, build_command)` | Build workspace (auto-detect if not provided) |
| `run_ship(workspace, instance_id, branch, domain)` | **Full pipeline: pack → push R2 → deploy to agent** |
| `check_deploy_status(instance_id)` | Query agent for current deploy state |
| `run_validation(workspace, checks)` | Run validation (validate.toml) |

**`run_ship` detailed flow**:
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

**Secrets tools** (tools/secrets.py):

| Tool | Purpose |
|------|---------|
| `list_secrets()` | List project secrets grouped by bucket |
| `add_secret(key, value)` | Add/update secret, auto-classify |

**Connector tools** (tools/connectors.py):

| Tool | Purpose |
|------|---------|
| `setup_connector(connector_id, config_json)` | Install connector (github, s3, slack, cloudflare, r2) |
| `list_connectors()` | List installed connectors + test status |

Connectors auto-sync to secrets: GitHub → GH_TOKEN/GH_REPO, S3/R2 → AWS keys, Slack → SLACK_TOKEN

**Infrastructure tools** (tools/infrastructure.py):

| Tool | Purpose |
|------|---------|
| `list_instances()` | List all instances + compute nodes |
| `create_instance(label, region, plan, workspace)` | Create Vultr VPS (guards against redundant creation) |
| `manage_service(target_id, action, service_name)` | Start/stop/restart systemd service via agent |
| `link_workspace_instance(workspace, instance_id)` | Link workspace to instance for auto-targeting |
| `manage_domain(workspace, action, custom_domain)` | Auto-assign/custom/remove domains |

**Mesh tools** (tools/mesh.py) — manages external servers (Hetzner, OVH, DO, bare metal, Raspberry Pi):

| Tool | Purpose |
|------|---------|
| `list_mesh_devices(status, tag)` | List external servers |
| `list_mesh_groups()` | List device groups |
| `register_mesh_device(name, host, ssh_port, ssh_user, tags)` | Register external server |
| `exec_on_mesh_device(device_id, command, timeout)` | SSH command on single device |
| `exec_on_mesh_group(group_id, command, timeout)` | SSH command on ALL devices concurrently |
| `deploy_to_mesh(workspace, target, target_dir, restart_command)` | Deploy .zar to device(s) via SCP |
| `mesh_device_status(device_id)` | Health + metrics |
| `manage_mesh_group(action, group_id, device_ids)` | Create/update device groups |

**Mesh deploy flow**: pack .zar → SCP to each target → extract → run restart_command

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

## API Routes — Central Server (:8000)

### Public
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/auth/login` | Login (admin or user) |
| POST | `/api/auth/register` | Create user account |
| POST | `/api/auth/verify-email` | Verify email token |
| POST | `/api/auth/resend-verification` | Resend verification email |
| POST | `/api/auth/forgot-password` | Request password reset |
| POST | `/api/auth/reset-password` | Reset password with token |
| GET | `/api/billing/plans` | List billing plans |
| GET | `/api/modules/catalog` | Public module catalog |

### Auth — user (requires user JWT)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/auth/me` | Get current user profile |
| PATCH | `/api/auth/profile` | Update name/email |
| POST | `/api/auth/change-password` | Change password |
| GET | `/api/auth/users` | List all users (admin only) |

### Projects (admin)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List all |
| POST | `/api/projects` | Create (returns API key) |
| GET | `/api/projects/{pid}` | Get details |
| DELETE | `/api/projects/{pid}` | Delete |
| POST | `/api/projects/{pid}/rotate-key` | Rotate API key |

### Instances (API key or admin)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/{pid}/instances` | List |
| POST | `/api/projects/{pid}/instances` | Create VPS |
| GET | `/api/projects/{pid}/instances/{iid}` | Details |
| DELETE | `/api/projects/{pid}/instances/{iid}` | Destroy |
| POST | `/api/projects/{pid}/instances/{iid}/start` | Start |
| POST | `/api/projects/{pid}/instances/{iid}/stop` | Stop |
| POST | `/api/projects/{pid}/instances/{iid}/exec` | Run command |

### Workspaces (API key or admin)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/{pid}/workspaces` | List |
| POST | `/api/projects/{pid}/workspaces` | Create |
| GET | `/api/projects/{pid}/workspaces/{name}` | Get details |
| DELETE | `/api/projects/{pid}/workspaces/{name}` | Delete |
| GET | `/api/projects/{pid}/workspaces/{name}/config` | Read config.toml |
| PUT | `/api/projects/{pid}/workspaces/{name}/config` | Update config (incl env vars) |
| GET | `/api/projects/{pid}/workspaces/{name}/files` | List files |
| POST | `/api/projects/{pid}/workspaces/{name}/files/read` | Read file |
| POST | `/api/projects/{pid}/workspaces/{name}/files/write` | Write file |

### Deploy — .zar (API key or admin)
| Method | Path | Description |
|--------|------|-------------|
| POST | `.../zar/{name}/pack` | Pack workspace into .zar |
| POST | `.../zar/{name}/push` | Push .zar to R2 |
| POST | `.../zar/{name}/deploy` | Deploy .zar to instance via agent |
| POST | `.../zar/{name}/ship` | All-in-one: pack + push + deploy |
| POST | `.../zar/{name}/rollback` | Rollback to previous snapshot |
| POST | `.../zar/{name}/branch` | Create branch |
| POST | `.../zar/{name}/merge` | Merge branches |
| GET | `.../zar/{name}/versions` | List versions/branches |
| POST | `.../zar/self-update` | Update agent/core/frontend on instance |

### Addons (connectors + plugins + marketplace)
| Method | Path | Description |
|--------|------|-------------|
| GET | `.../addons?addon_type=` | List addons (filtered by type) |
| GET | `.../addons/catalog?addon_type=` | List catalog (admin) |
| POST | `.../addons/catalog` | Publish addon (admin) |
| PATCH | `.../addons/catalog/{type}/{id}` | Update catalog entry (admin) |
| DELETE | `.../addons/catalog/{type}/{id}` | Remove from catalog (admin) |
| POST | `.../addons/install?addon_type=` | Install addon |
| PATCH | `.../addons/{id}?addon_type=` | Enable/disable, update config |
| DELETE | `.../addons/{id}?addon_type=` | Uninstall addon |
| GET | `.../addons/connectors/{id}/status` | Connector connection status |
| POST | `.../addons/connectors/{id}/test` | Test connector connection |

### Plugin APIs (API key, requires plugin installed)
| Method | Path | Description |
|--------|------|-------------|
| GET | `.../p/storage/files` | List storage files |
| POST | `.../p/storage/upload` | Upload file to R2 |
| GET | `.../p/storage/download` | Download file |
| DELETE | `.../p/storage/files` | Delete file |
| GET | `.../p/logs` | Get deploy logs |
| GET/POST/DELETE | `.../p/dns/records` | DNS record CRUD |
| GET | `.../p/monitoring/instances` | Instance monitoring |
| GET | `.../p/backups/list` | List .zar backups |

### Domains (API key or admin)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/{pid}/domains` | List |
| POST | `/api/projects/{pid}/domains` | Add domain |
| DELETE | `/api/projects/{pid}/domains/{id}` | Remove |

### Billing (user JWT or admin)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/billing/plans` | List plans (public) |
| GET | `/api/billing/subscription` | Current subscription |
| POST | `/api/billing/subscribe` | Subscribe (free plans) |
| POST | `/api/billing/cancel` | Cancel subscription |
| POST | `/api/billing/pause` | Pause subscription |
| POST | `/api/billing/resume` | Resume subscription |
| POST | `/api/billing/checkout` | Stripe checkout (paid plans) |
| POST | `/api/billing/topup/checkout` | Stripe wallet top-up |
| POST | `/api/billing/stripe/webhook` | Stripe webhook handler |
| GET | `/api/billing/invoices` | List invoices |
| GET | `/api/billing/invoices/{id}` | Get invoice details |
| POST | `/api/billing/invoices/generate` | Generate draft invoice |
| POST | `/api/billing/invoices/{id}/finalize` | Finalize invoice (admin) |
| POST | `/api/billing/invoices/{id}/void` | Void invoice (admin) |
| GET | `/api/billing/wallets` | List wallets |
| POST | `/api/billing/wallets` | Create wallet |
| GET | `/api/billing/wallets/{id}` | Get wallet |
| POST | `/api/billing/wallets/{id}/topup` | Top up wallet |
| GET | `/api/billing/wallets/{id}/transactions` | Wallet transactions |
| GET/POST | `/api/billing/coupons` | Coupon CRUD (admin) |
| POST | `/api/billing/coupons/apply` | Apply coupon code |
| GET/POST | `/api/billing/credit-notes` | Credit note CRUD |
| GET/POST/PATCH/DELETE | `/api/billing/metrics` | Billable metrics (admin) |
| POST | `/api/billing/usage` | Record usage event |
| GET | `/api/billing/usage/summary` | Usage summary for current period |
| GET/POST/PATCH | `/api/billing/taxes` | Tax rates (admin) |
| GET/DELETE/POST | `/api/billing/payment-methods` | Payment method management |
| GET | `/api/billing/events` | Billing events (admin) |
| GET | `/api/billing/overview` | Full billing overview |

### Notifications (user JWT)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/notifications` | List notifications |
| POST | `/api/notifications/{id}/read` | Mark read |
| POST | `/api/notifications/read-all` | Mark all read |
| DELETE | `/api/notifications/{id}` | Delete notification |
| POST | `/api/notifications` | Send notification (admin) |

### Subdomain (user JWT)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/subdomain` | Get user's subdomain |
| GET | `/api/subdomain/check` | Check availability |
| POST | `/api/subdomain/claim` | Claim subdomain |

### Modules (admin for management, public catalog)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/modules/catalog` | Public module catalog |
| GET | `/api/modules/catalog/{name}` | Get module details |
| GET | `/api/modules` | List all modules (admin) |
| POST | `/api/modules` | Publish module (admin) |
| POST | `/api/modules/{name}/upload` | Upload .zar package (admin) |
| GET | `/api/modules/{name}/versions` | List versions |
| GET | `/api/modules/{name}/download` | Download info |
| PATCH | `/api/modules/{name}` | Update module (admin) |
| DELETE | `/api/modules/{name}` | Remove module (admin) |

### Admin Panel (admin only, restricted to sonfazt.nso.dev)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/overview` | Dashboard overview |
| GET | `/api/admin/users` | List users with search/pagination |
| GET | `/api/admin/users/{uid}` | Full user details |
| PATCH | `/api/admin/users/{uid}` | Update user fields |
| POST | `/api/admin/users/{uid}/reset-password` | Reset user password |
| POST | `/api/admin/users/{uid}/disable` | Disable user account |
| GET | `/api/admin/users/{uid}/activity` | User activity log |
| GET | `/api/admin/analytics/revenue` | Revenue summary |
| GET | `/api/admin/analytics/growth` | User growth metrics |
| GET | `/api/admin/analytics/activity` | Platform-wide activity |
| GET | `/api/admin/analytics/cashflow` | Cashflow analysis |
| POST | `/api/admin/analytics/snapshot` | Generate analytics snapshot |
| POST | `/api/admin/fraud/scan` | Run fraud detection |
| GET | `/api/admin/ledger/stats` | Global ledger stats |
| GET | `/api/admin/ledger/users/{uid}` | User's blockchain ledger |
| POST | `/api/admin/ledger/users/{uid}/verify` | Verify user chain |
| POST | `/api/admin/ledger/verify-all` | Verify all chains |
| GET | `/api/admin/ledger/users/{uid}/balance-proof` | Cryptographic balance proof |
| GET | `/api/admin/ledger/discrepancies` | Find balance discrepancies |

## API Routes — Agent (:8081)

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Get JWT token (PBKDF2 + HS256) |
| GET | `/auth/me` | Check auth status |

### Files
| Method | Path | Description |
|--------|------|-------------|
| GET | `/files/list?path=` | Browse directory (type, size, perms, mtime) |
| GET | `/files/read?path=` | Read file content (max 5MB, blocks sensitive) |
| POST | `/files/write` | Write file (creates parent dirs, blocks protected) |
| POST | `/files/mkdir` | Create directory |
| DELETE | `/files/?path=` | Delete file/dir |
| GET | `/files/tree?path=&depth=` | Recursive tree (depth 1-5) |

### Exec
| Method | Path | Description |
|--------|------|-------------|
| POST | `/exec/` | Execute command (blacklist-filtered, 1-300s timeout) |
| POST | `/exec/service?action=&name=` | Manage systemd service (nso/nso-agent/nginx) |

### Secrets
| Method | Path | Description |
|--------|------|-------------|
| GET | `/secrets/scopes` | List all scopes (general + domains) |
| POST | `/secrets/scopes` | Create domain scope |
| DELETE | `/secrets/scopes/{domain}` | Delete scope |
| GET | `/secrets?scope=` | List all, grouped by bucket |
| POST | `/secrets?scope=` | Add secret (validates key format) |
| PUT | `/secrets/{key}?scope=` | Update secret value |
| DELETE | `/secrets/{key}?scope=` | Remove secret |

### Deploy
| Method | Path | Description |
|--------|------|-------------|
| POST | `/deploy/pull` | Download .zar from R2 and deploy (+ pipeline if deploy.toml) |
| POST | `/deploy/upload` | Receive .zar via multipart |
| POST | `/deploy/rollback` | Restore previous snapshot |
| GET | `/deploy/current` | Current deploy state + all versions |
| GET | `/deploy/snapshots` | List snapshots |
| POST | `/deploy/self-update` | Update agent itself |
| POST | `/deploy/setup-domain` | Auto-generate nginx config + SSL cert |
| GET | `/deploy/progress` | Poll SSE progress during active deploys |
| POST | `/platform-update` | Pull latest code, rebuild dashboards, restart services |

### Supervisor
| Method | Path | Description |
|--------|------|-------------|
| GET | `/supervisor/status` | All process states |
| POST | `/supervisor/apply` | Apply desired process specs |

### Pool VMs
| Method | Path | Description |
|--------|------|-------------|
| POST | `/pool/vms` | Create VM (Docker or cgroup sandbox) |
| GET | `/pool/vms` | List all VMs |
| GET | `/pool/vms/{vm_id}` | Get VM status |
| DELETE | `/pool/vms/{vm_id}` | Destroy VM + cleanup firewall |

### AI
| Method | Path | Description |
|--------|------|-------------|
| POST | `/ai/run` | Execute AI model request, store output files |
| GET | `/ai/assets` | List stored AI output files |

### Metrics
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Agent health + system metrics (public) |
| POST | `/report` | Report install progress (public, token-guarded) |
| POST | `/register` | Register instance for tracking |
| GET | `/status/{iid}` | Get install metrics |
| DELETE | `/status/{iid}` | Remove metrics |

## .zar System

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

### Deploy Flow
```
pack workspace → push .zar to R2 → agent pulls from R2 → snapshot existing
→ extract .zar → detect stack → install deps → run pipeline (if deploy.toml)
→ hand off to supervisor → health check → READY
```

### Workspace Dependencies
Workspaces depend on others via `[package.dependencies]` in config.toml.
Resolved recursively (max depth 5) from R2.

## Database Tables

```
AUTH (2)
├── users                    — accounts (email, password_hash, role, balance, subdomain)
└── email_tokens             → users CASCADE — verification/reset tokens

PROJECTS (2)
├── projects                 — metadata + api_key_hash (UNIQUE)
└── project_secrets          → projects CASCADE — per-project env vars (UNIQUE project+key+scope)

COMPUTE (6)
├── instances                → projects CASCADE — VPS instances (state machine)
├── instance_metrics         → instances CASCADE (UNIQUE instance_id) — CPU/mem/disk
├── compute_hosts            — multi-tenant host machines (no FK)
├── compute_vms              → hosts FK, projects FK — tenant VMs
├── compute_plans            — VM plan catalog (standalone)
└── compute_quotas           → projects CASCADE — per-project VM limits

WORKSPACE (3)
├── workspaces               → projects CASCADE (UNIQUE project+name)
├── workspace_shares         → workspaces CASCADE — join codes
└── workspace_members        → workspaces CASCADE, users CASCADE — collaboration

DNS (1)
└── domains                  → projects CASCADE, instances CASCADE

DEPLOY (3)
├── deploy_logs              → instances CASCADE — deploy log entries
├── deploy_threads           → projects CASCADE — AI deploy conversations
└── deploy_messages          → deploy_threads CASCADE — thread messages

BUILD (2)
├── build_cache              → projects CASCADE (UNIQUE project+workspace+hash)
└── build_logs               → projects CASCADE

ORCHESTRATOR (10)
├── instance_pool            → instances CASCADE (UNIQUE instance_id) — build nodes
├── build_queue              → projects CASCADE, instance_pool SET NULL
├── orchestrator_alerts      → instance_pool CASCADE
├── lb_pools                 — load balancer pools
├── lb_backends              → lb_pools CASCADE, instances CASCADE
├── lb_rules                 → lb_pools CASCADE — routing rules
├── instance_specs           — desired state
├── workspace_specs          — desired state
├── system_specs             — desired state (project_id PK)
└── reconcile_log            — reconciliation audit (standalone)

BILLING (15)
├── billing_plans            — plan catalog (UNIQUE code, standalone)
├── billing_subscriptions    → users CASCADE, plans RESTRICT
├── billing_invoices         → users CASCADE
├── billing_invoice_items    → invoices CASCADE
├── billing_payment_methods  → users CASCADE — Stripe methods
├── billing_usage_events     → users CASCADE
├── billing_coupons          — coupon definitions (UNIQUE code)
├── billing_applied_coupons  → users CASCADE, coupons CASCADE
├── billing_credit_notes     → users CASCADE, invoices SET NULL
├── billing_billable_metrics — metric definitions (UNIQUE code)
├── billing_taxes            — tax rates (UNIQUE code)
├── billing_wallets          → users CASCADE — prepaid credit
├── billing_wallet_transactions → wallets CASCADE
├── billing_events           → users CASCADE — audit trail
└── transactions (legacy)    → users CASCADE

ADDONS
├── addon_catalog            — standalone (UNIQUE addon_id+type)
├── addons                   → projects CASCADE (UNIQUE project+addon_id+type)
├── modules                  — system module catalog (UNIQUE name)
├── webhook_configs          → projects CASCADE
├── webhook_deliveries       → webhook_configs CASCADE
├── uptime_targets           → projects CASCADE
├── uptime_results           → uptime_targets CASCADE
├── ssl_certificates         → projects CASCADE
├── scheduled_tasks          → projects CASCADE, instances CASCADE
└── task_executions          → scheduled_tasks CASCADE

ADMIN (3)
├── ledger_blocks            → users CASCADE — blockchain audit trail
├── activity_log             → users CASCADE — user actions
└── analytics_snapshots      — periodic snapshots (standalone)

NOTIFICATIONS (1)
└── notifications            → users CASCADE — inbox

VALIDATOR (3)
├── validations              → projects CASCADE (UNIQUE project+name)
├── validation_runs          → projects CASCADE
└── validation_results       → validation_runs CASCADE

INFRASTRUCTURE (2)
├── managed_databases        → projects CASCADE, instances CASCADE
└── storage_buckets          → projects CASCADE (UNIQUE project+name)

SYSTEM (1)
└── system_events            — event log (standalone)
```

## Environment Variables

```bash
# Vultr
VULTR_API_KEY=...
VULTR_DEFAULT_REGION=ewr          # optional
VULTR_DEFAULT_PLAN=vc2-1c-1gb     # optional
VULTR_DEFAULT_OS=2136             # optional

# Cloudflare
CF_API_TOKEN=...
CF_NSO_ZONE_ID=...                # for subdomain DNS management
NSO_BASE_DOMAIN=nso.dev           # base domain for user subdomains

# R2 Storage
R2_ENDPOINT=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=nso
R2_PUBLIC_URL=...                 # optional, for public download URLs

# Central Server
NSO_HOST=0.0.0.0
NSO_PORT=8000
NSO_CORS_ORIGINS=https://nso.dev,http://localhost:3000
NSO_DATA_DIR=/opt/nso/data
NSO_CONFIG_DIR=/opt/nso/config
NSO_WORKSPACES_DIR=/opt/nso/workspaces
DATABASE_URL=postgresql://nso:pass@localhost:5432/nso

# Admin
NSO_ADMIN_EMAIL=...
NSO_ADMIN_PASSWORD=...

# Agent
AGENT_ADMIN_PASSWORD=...

# JWT (REQUIRED in production — auto-generated in dev but invalidates on restart)
NSO_JWT_SECRET=...

# Email (optional — emails are no-op if not configured)
SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
SMTP_FROM=nso@nso.dev
NSO_EMAIL_SECRET=...           # auto-generated if not set

# Stripe (optional — for paid billing)
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_PUBLISHABLE_KEY=...

# PostgreSQL (set via setup-postgres.sh or install.sh --central)
DB_PASSWORD=...                # auto-generated during setup
```

## Project Structure

```
setupo/
├── nso/                         # Central server (modular engine architecture)
│   ├── __init__.py
│   ├── main.py                  # Auto-discovery entry point (scans engine/*/config.toml)
│   ├── config.py                # Settings from env (all config centralized)
│   ├── config.toml              # Project metadata
│   ├── shared/                  # Cross-cutting infrastructure
│   │   ├── db.py                # PostgreSQL persistence (asyncpg) + generic CRUD
│   │   ├── models.py            # Shared Pydantic models (R2Config, etc.)
│   │   ├── errors.py            # Exception hierarchy (NsoError tree)
│   │   ├── deps.py              # Shared FastAPI dependencies (require_admin, etc.)
│   │   ├── ratelimit.py         # Rate limiting middleware
│   │   └── auth/                # Auth infrastructure
│   │       ├── jwt.py           # User JWT + PBKDF2 password hashing
│   │       ├── keys.py          # API key generation (sk_live_)
│   │       └── resolve.py       # Token resolution + AuthContext
│   └── engine/                  # Modular business logic (15 modules)
│       ├── auth/                # Users, login, registration, subdomain
│       ├── billing/             # Plans, subscriptions, wallets, invoices, Stripe
│       ├── compute/             # Instance CRUD, lifecycle, providers (Vultr, CF)
│       ├── deploy/              # Deploy pipeline, sync, config
│       ├── deploy_agent/        # AI-powered deploy assistant
│       ├── storage/             # R2 client, .zar packing/resolving
│       ├── workspace/           # Workspace config, files, sharing, platform workspaces
│       ├── projects/            # Project CRUD
│       ├── dns/                 # Domains, subdomain DNS
│       ├── addons/              # Plugins, connectors, marketplace, AI apps
│       ├── admin/               # Analytics, blockchain ledger, fraud detection
│       ├── notifications/       # Email service, notification inbox
│       ├── orchestrator/        # Scheduler, pool, scaler, load balancer, reconciler
│       ├── secrets/             # Project secret management
│       └── infrastructure/      # Managed databases, storage buckets
│       # Each module: config.toml, routes.py, service.py, migrations.py
│
├── vm/                          # VM-side code (agent + CLI)
│   ├── agent/                   # NSO Agent (runs on each VPS :8081)
│   │   ├── main.py              # Agent entry + lifespan (init store, restore VMs, start supervisor)
│   │   ├── auth.py              # Agent-local JWT auth (PBKDF2 100k iter, HS256, 7-day expiry)
│   │   ├── files.py             # Sandboxed file ops (ALLOWED_ROOTS, 5MB limit, sensitive block)
│   │   ├── exec.py              # Command execution (blacklist, 4096 char limit, env injection block)
│   │   ├── deploy.py            # .zar deploy (R2 SigV4 download, snapshot, rollback, self-update)
│   │   ├── pipeline.py          # 10-phase deploy pipeline (deploy.toml, template interp, rollback)
│   │   ├── supervisor.py        # Process lifecycle (reconcile 5s, health 10s, blue-green, auto-rollback)
│   │   ├── pool_handler.py      # Multi-tenant VM (Docker hardened + cgroup sandbox, iptables isolation)
│   │   ├── ai.py                # AI model execution proxy (Baseten, asset storage, context injection)
│   │   ├── envvars.py           # Env var CRUD (scopes: general + per-domain, bucket auto-classify)
│   │   ├── store.py             # SQLite metrics (10 boot stages, progress tracking)
│   │   └── models.py            # Pydantic models (Stage enum, MetricReport, InstanceMetrics)
│   ├── cli/                     # Python CLI package
│   │   ├── main.py              # Commands + argument parser
│   │   ├── client.py            # HTTP client (auth, retries, timeouts)
│   │   └── output.py            # Terminal formatting helpers
│   ├── nso                      # CLI entry point
│   └── config.toml              # VM workspace config
│
├── client/                      # Frontend dashboards
│   ├── dashboard/               # Main Next.js dashboard
│   │   └── src/
│   │       ├── app/             # Next.js app router
│   │       ├── components/dashboard/  # All panels
│   │       ├── lib/api/client.ts      # API client
│   │       ├── stores/                # Zustand state
│   │       └── types/                 # TypeScript types
│   └── admin/                   # Admin Next.js dashboard
│       └── src/
│
├── nso/base/                    # Server setup & operations scripts
│   ├── install.sh               # Installer (--central for PostgreSQL; fallback: git clone)
│   ├── setup-postgres.sh        # Standalone PostgreSQL 16 setup + tuning
│   ├── migrate-sqlite-to-pg.py  # SQLite → PostgreSQL data migration (async, idempotent)
│   ├── cloud-init.yaml          # Cloud-init for user VPS instances
│   └── cloud-init-pool-host.yaml # Cloud-init for pool/build host VMs
│
├── tests/                       # Test suite (pytest)
├── requirements.txt
├── pytest.ini
├── CLAUDE.md                    # This file
└── DEPLOY.md                    # Deploy guide
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, asyncpg (PostgreSQL), aiosqlite (agent)
- **Frontend**: Next.js 16 (dashboard), Next.js 15 (admin)
- **Database**: PostgreSQL 16 (central server), SQLite (agent per VPS)
- **Storage**: Cloudflare R2 (S3v4 HMAC signing, no boto3)
- **Providers**: Vultr (VPS provisioning), Cloudflare (DNS + R2)
- **Payments**: Stripe (checkout sessions, webhooks)
- **Email**: SMTP (verification, password reset, notifications)
- **Deploy**: cloud-init (bootstrap), systemd, nginx reverse proxy, .zar packages
- **CLI**: Python (rich, httpx)
- **State**: Zustand (frontend), event bus (backend pub/sub)

## Common Commands

```bash
# Run central server (dev)
cd /opt/nso && venv/bin/uvicorn nso.main:app --reload --port 8000

# Run agent (dev)
cd /opt/nso/vm/agent && ../../venv/bin/uvicorn main:app --port 8081

# Build dashboard
cd client/dashboard && npm run build && npm run export

# Build admin
cd client/admin && npm run build && npm run export

# Ship workspace (pack + push + deploy)
nso ship my-workspace inst_xxx

# Or via API
curl -X POST -H "Authorization: Bearer sk_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"inst_xxx"}' \
  https://nso.dev/api/projects/{pid}/zar/{name}/ship

# Restart services
systemctl restart nso nso-agent

# Check status
systemctl status nso nso-agent nginx postgresql

# View logs
journalctl -u nso -f
journalctl -u nso-agent -f

# Install from git (no nso.dev needed)
git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git
cd setupo && bash nso/base/install.sh --central --email admin@nso.dev

# PostgreSQL setup (existing VPS, migrate from SQLite)
bash nso/base/setup-postgres.sh --migrate /opt/nso/data/nso.db
```

## VPS Directory Layout

```
/opt/nso/
├── config/
│   ├── agent.env           # Agent: JWT_SECRET, AGENT_ADMIN_PASSWORD, DATABASE_URL
│   └── nso.env             # Central: DATABASE_URL, provider keys
├── data/
│   ├── nso.db              # SQLite (legacy/agent-only)
│   ├── metrics.db           # SQLite metrics store (boot progress)
│   ├── deploy-state.json    # Current deploy state (fcntl locked)
│   ├── supervisor-state.json # Process supervisor state
│   └── rollback-request.json # Auto-rollback trigger (>50% process failure)
├── workspaces/             # Deployed workspace files
│   └── default/static/     # Default landing page
├── venv/                   # Python virtualenv (FastAPI, uvicorn, asyncpg, etc.)
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
