# Setupo — AI Agent Infrastructure Platform

## Infrastructure

| Detail | Value |
|--------|-------|
| Main VPS | 65.20.102.242 (zarnetti.com) |
| Test VPS | 65.20.103.88 (Rust HTTP on :3000) |
| Provider | Vultr (VPS) + Cloudflare (DNS + R2) |
| Repo | github.com/lailaelghazouanitecnologia-cloud/setupo |
| Project ID | `proj_0f71067738c73681` |
| Project name | mesh-test |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CENTRAL SERVER (:8000)                        │
│                                                                 │
│  dashboard/ (Next.js)          server/ (FastAPI)                │
│  ├── src/app/                  ├── main.py (entry)              │
│  ├── src/components/           ├── config.py (env vars)         │
│  │   └── dashboard/            ├── deps.py (auth deps)          │
│  │       ├── inbox-panel       ├── auth/                        │
│  │       ├── instances-panel   │   ├── keys.py (sk_live_ gen)   │
│  │       ├── projects-panel    │   └── middleware.py (resolve)   │
│  │       ├── deploy-panel      └── routes/                      │
│  │       ├── secrets-panel         ├── health.py                │
│  │       └── plugins-panel         ├── auth.py                  │
│  ├── src/lib/api/client.ts         ├── projects.py              │
│  └── src/stores/                   ├── instances.py             │
│                                    ├── workspaces.py            │
│  core/                             ├── domains.py               │
│  ├── db.py (SQLite)                ├── deploy.py                │
│  ├── models.py (Pydantic)          ├── zar.py                   │
│  ├── errors.py                     └── plugins.py (catalog+user)│
│  ├── workspace_config.py                                        │
│  ├── deploy/ (orchestration)   Cloudflare R2                    │
│  ├── instances/ (lifecycle)    ├── .zar packages                │
│  ├── projects/ (CRUD)          ├── branches.json                │
│  ├── providers/ (Vultr, CF)    └── latest.zar per branch        │
│  └── zar/ (packer, storage)                                     │
└───────────────────────┬─────────────────────────────────────────┘
                        │  HTTP (no SSH)
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                   NSO AGENT (per VPS :8081)                      │
│                                                                 │
│  nso-agent/                                                     │
│  ├── main.py       (entry, router mounting)                     │
│  ├── auth.py       (JWT login, PBKDF2)                          │
│  ├── files.py      (browse/read/write/delete)                   │
│  ├── exec.py       (command execution)                          │
│  ├── deploy.py     (pull .zar, snapshot, rollback, self-update) │
│  ├── secrets.py    (env var CRUD, bucket grouping)              │
│  ├── store.py      (SQLite metrics)                             │
│  └── models.py                                                  │
│                                                                 │
│  nginx → /api/ (:8000) + /agent/ (:8081) + / (static dashboard)│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   NSO CLIENT (future)                            │
│  Rust TUI binary — downloadable from dashboard                  │
│  Commands: nso login, nso ship, nso exec, nso inst              │
└─────────────────────────────────────────────────────────────────┘
```

## Authentication

Three auth mechanisms:

| Type | Format | Scope | How to get |
|------|--------|-------|-----------|
| Admin token | random 64 chars (file-backed) | Full platform access | `POST /api/auth/login` |
| Project API key | `sk_live_xxxx` (SHA256 in DB) | Single project | Created with project, rotatable |
| Agent JWT | `header.payload.sig` (HS256) | Agent endpoints on VPS | `POST /agent/auth/login` |

### Login flow (dashboard)

```
Browser → POST /agent/auth/login  → JWT → localStorage["nso_token"]
       → POST /api/auth/login    → admin token → localStorage["nso_api_token"]
```

The dashboard uses **two tokens simultaneously**:
- `nso_token` → agent calls (files, exec, secrets, deploy)
- `nso_api_token` → central API calls (projects, workspaces, instances, plugins)

### Dependency injection (server/deps.py)

```python
require_project  → API key provides project_id; admin gets it from URL
require_admin    → Admin token only
```

## Nginx Routing

```
Client (HTTPS :443 → zarnetti.com)
    ├── /api/*      → proxy_pass 127.0.0.1:8000  (FastAPI central)
    ├── /agent/*    → proxy_pass 127.0.0.1:8081/ (nso-agent)
    ├── /ws/*       → WebSocket proxy :8000
    └── /           → /opt/setupo/dashboard/static (Next.js export)
```

## API Routes — Central Server (:8000)

### Public
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | Get admin token |
| GET | `/api/health` | Health check |

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

### Plugins (admin for catalog, API key for install)
| Method | Path | Description |
|--------|------|-------------|
| GET | `.../plugins/catalog` | List catalog (admin, includes unpublished) |
| POST | `.../plugins/catalog` | Publish plugin to catalog (admin) |
| PATCH | `.../plugins/catalog/{id}` | Update catalog entry (admin) |
| DELETE | `.../plugins/catalog/{id}` | Remove from catalog (admin) |
| GET | `.../plugins` | List available + install status (user) |
| POST | `.../plugins/install` | Install plugin (user) |
| PATCH | `.../plugins/{id}` | Enable/disable, update config (user) |
| DELETE | `.../plugins/{id}` | Uninstall (user) |

### Domains (API key or admin)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/{pid}/domains` | List |
| POST | `/api/projects/{pid}/domains` | Add domain |
| DELETE | `/api/projects/{pid}/domains/{id}` | Remove |

## API Routes — Agent (:8081)

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Get JWT token |
| GET | `/auth/me` | Check auth status |

### Files
| Method | Path | Description |
|--------|------|-------------|
| GET | `/files/list?path=` | Browse directory |
| GET | `/files/read?path=` | Read file content |
| POST | `/files/write` | Write file |
| POST | `/files/mkdir` | Create directory |
| DELETE | `/files/?path=` | Delete file/dir |
| GET | `/files/tree?path=&depth=` | Directory tree |

### Exec
| Method | Path | Description |
|--------|------|-------------|
| POST | `/exec/` | Execute command |
| POST | `/exec/service?action=&name=` | Manage systemd service |

### Secrets (env var management)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/secrets` | List all, grouped by bucket |
| POST | `/secrets` | Add secret (validates key format) |
| PUT | `/secrets/{key}` | Update secret value |
| DELETE | `/secrets/{key}` | Remove secret |
| GET | `/secrets/buckets` | List bucket definitions |

Buckets auto-classify by prefix:
- **auth**: `SETUPO_ADMIN_*`, `AGENT_ADMIN_*`, `JWT_*`, `SECRET_*`
- **providers**: `VULTR_*`, `CF_*`
- **storage**: `R2_*`
- **system**: `HOST*`, `PORT*`, `DB_*`, `LOG_*`, `CORS_*`
- **custom**: everything else

### Deploy
| Method | Path | Description |
|--------|------|-------------|
| POST | `/deploy/pull` | Download .zar from R2 and deploy |
| POST | `/deploy/upload` | Receive .zar via multipart |
| POST | `/deploy/rollback` | Restore previous snapshot |
| GET | `/deploy/current` | Current deploy state |
| GET | `/deploy/snapshots` | List snapshots |
| POST | `/deploy/self-update` | Update agent itself |

### Metrics
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Agent health (public) |
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
```

### Deploy Flow
```
pack workspace → push .zar to R2 → agent pulls from R2 → snapshot → extract → restart
```

### Workspace Dependencies
Workspaces depend on others via `[package.dependencies]` in config.toml.
Resolved recursively (max depth 5) from R2.

## Database Tables

| Table | Purpose |
|-------|---------|
| `projects` | Project metadata + API key hash |
| `instances` | VPS instances per project |
| `domains` | Domain records per project |
| `plugins` | Installed plugins per project |
| `plugin_catalog` | Admin-published plugin definitions |

## Environment Variables

```bash
# Vultr
VULTR_API_KEY=...

# Cloudflare
CF_API_TOKEN=...

# R2 Storage
R2_ENDPOINT=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=nso

# Admin
SETUPO_ADMIN_EMAIL=...
SETUPO_ADMIN_PASSWORD=...

# Agent
AGENT_ADMIN_PASSWORD=...
NSO_ADMIN_EMAIL=...
```

## Project Structure

```
setupo/
├── core/                    # Core business logic
│   ├── db.py               # SQLite persistence (aiosqlite)
│   ├── models.py           # All Pydantic models
│   ├── errors.py           # Exception hierarchy
│   ├── workspace_config.py # config.toml reader/writer
│   ├── deploy/             # Deploy orchestration
│   ├── instances/          # Instance CRUD + lifecycle
│   ├── projects/           # Project CRUD
│   ├── providers/          # Vultr + Cloudflare clients
│   └── zar/                # .zar packaging system
│       ├── packer.py       # Pack/extract .zar archives
│       ├── storage.py      # R2 client (S3v4 signing)
│       └── resolver.py     # Dependency resolution
├── server/                  # FastAPI HTTP layer
│   ├── main.py             # App entry, middleware, router mounting
│   ├── config.py           # Settings from env
│   ├── deps.py             # Shared FastAPI dependencies
│   ├── auth/               # Auth system
│   │   ├── keys.py         # API key generation (sk_live_)
│   │   └── middleware.py   # Token resolution + AuthContext
│   └── routes/             # All API route handlers
│       ├── auth.py         # Login endpoint
│       ├── health.py       # Health check
│       ├── projects.py     # Project CRUD
│       ├── instances.py    # Instance lifecycle
│       ├── workspaces.py   # Workspace management
│       ├── domains.py      # Domain management
│       ├── deploy.py       # Deploy orchestration
│       ├── zar.py          # .zar pack/push/deploy/ship
│       └── plugins.py      # Plugin catalog (admin) + install (user)
├── nso-agent/               # VPS agent (runs on each instance)
│   ├── main.py             # Agent entry
│   ├── auth.py             # Agent-local JWT auth (PBKDF2)
│   ├── files.py            # File operations (browse/read/write/delete)
│   ├── exec.py             # Command execution
│   ├── deploy.py           # .zar deploy/snapshot/rollback
│   ├── secrets.py          # Env var CRUD with bucket grouping
│   ├── store.py            # SQLite metrics store
│   └── models.py           # Agent models
├── dashboard/               # Next.js admin dashboard
│   └── src/
│       ├── app/            # Next.js app router
│       ├── components/
│       │   └── dashboard/
│       │       ├── dashboard-layout.tsx  # Main layout + sidebar + header
│       │       ├── inbox-panel.tsx       # Notifications
│       │       ├── instances-panel.tsx   # Instance management
│       │       ├── projects-panel.tsx    # Project + workspace management
│       │       ├── deploy-panel.tsx      # Deploy UI
│       │       ├── secrets-panel.tsx     # Secrets with bucket groups
│       │       └── plugins-panel.tsx     # Plugin catalog + install
│       ├── lib/api/client.ts            # API client (agent + central)
│       ├── stores/dashboard-store.ts    # Zustand state
│       └── types/dashboard.ts           # TypeScript types
├── deploy/                  # Production deploy configs
│   ├── bootstrap.sh        # Full Debian 12 VPS bootstrap
│   ├── nginx.conf          # Nginx reverse proxy config
│   ├── setupo.service      # Main API systemd unit
│   └── setupo-agent.service # Agent systemd unit
├── base/
│   ├── cloud-init.yaml     # VPS provisioning template
│   └── scripts/bootstrap.sh # Post-boot verification
├── workspaces/              # Workspace files (on VPS)
├── .env.example
├── requirements.txt
├── PLAN.md                  # Roadmap
└── CLAUDE.md                # This file — architecture reference
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, aiosqlite, httpx
- **Frontend**: Next.js (dashboard), Vite+React (workspace default)
- **Database**: SQLite (async via aiosqlite)
- **Storage**: Cloudflare R2 (S3v4 HMAC signing, no boto3)
- **Providers**: Vultr (VPS), Cloudflare (DNS)
- **Deploy**: cloud-init (bootstrap), systemd, nginx reverse proxy
- **Future CLI**: Rust (tokio, ratatui)

## Common Commands

```bash
# Run API server (dev)
cd /opt/setupo && venv/bin/uvicorn server.main:app --reload --port 8000

# Run agent (dev)
cd /opt/setupo/nso-agent && ../venv/bin/uvicorn main:app --port 8081

# Build dashboard
cd dashboard && npm run build

# Ship (pack + push + deploy)
curl -X POST -H "Authorization: Bearer sk_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"inst_xxx"}' \
  https://zarnetti.com/api/projects/{pid}/zar/{name}/ship

# Restart services
systemctl restart setupo setupo-agent
```
