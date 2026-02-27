# Setupo — AI Agent Infrastructure Platform

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CENTRAL SERVER                           │
│                                                                 │
│  dashboard/ (Next.js :3000)    server/ (FastAPI :8000)          │
│  ├── src/app/                  ├── main.py (entry)              │
│  ├── src/components/           ├── config.py (env vars)         │
│  ├── src/lib/api.ts            ├── deps.py (auth deps)         │
│  └── src/stores/               ├── auth/ (JWT + API keys)      │
│                                └── routes/                      │
│                                    ├── health.py                │
│                                    ├── auth.py                  │
│                                    ├── projects.py              │
│                                    ├── instances.py             │
│                                    ├── workspaces.py            │
│                                    ├── domains.py               │
│                                    ├── deploy.py                │
│                                    └── zar.py ← .zar packaging  │
│                                                                 │
│  core/                         Cloudflare R2                    │
│  ├── db.py (SQLite)            ├── .zar packages                │
│  ├── models.py (Pydantic)      ├── branches.json               │
│  ├── errors.py                 └── latest.zar per branch       │
│  ├── workspace_config.py                                        │
│  ├── deploy/ (orchestration)                                    │
│  ├── instances/ (lifecycle)                                     │
│  ├── projects/ (CRUD)                                           │
│  ├── providers/ (Vultr, CF)                                     │
│  └── zar/ (packer, storage, resolver)                           │
└───────────────────────┬─────────────────────────────────────────┘
                        │  HTTP (no SSH)
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                     VPS (per instance)                           │
│                                                                 │
│  nso-agent/ (FastAPI :8081) ← "the agent"                    │
│  ├── main.py (entry)                                            │
│  ├── auth.py (JWT login)                                        │
│  ├── files.py (browse/read/write/delete)                        │
│  ├── exec.py (command execution)                                │
│  ├── deploy.py (pull .zar, snapshot, rollback, self-update)     │
│  ├── store.py (SQLite metrics)                                  │
│  └── models.py                                                  │
│                                                                 │
│  nginx → :8000 (API) + :8081 (agent) + static dashboard        │
└─────────────────────────────────────────────────────────────────┘
```

## Key Concepts

### Authentication
- **Admin**: Bearer token (JWT) via `POST /api/auth/login`
- **Project API keys**: `sk_live_xxx` scoped to a single project
- **Agent auth**: JWT via `POST /agent/auth/login` on each VPS

### Deploy Flow (new — .zar system)
```
pack workspace → push .zar to R2 → agent pulls from R2 → snapshot → extract → restart
```
No SSH. No instance recreation. The nso-agent agent handles everything.

### .zar Format
A tar.gz with this structure:
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

### Workspace Dependencies
Workspaces can depend on other workspaces via `[package.dependencies]` in config.toml.
Resolved recursively (max depth 5) from R2.

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, aiosqlite, httpx
- **Frontend**: Next.js (dashboard), Vite+React (workspace default)
- **Database**: SQLite (async via aiosqlite)
- **Storage**: Cloudflare R2 (S3v4 HMAC signing, no boto3)
- **Providers**: Vultr (VPS), Cloudflare (DNS)
- **Deploy**: cloud-init (bootstrap), systemd, nginx reverse proxy

## API Routes

| Prefix | Module | Auth |
|--------|--------|------|
| `POST /api/auth/login` | auth.py | Public |
| `GET /api/health` | health.py | Public |
| `/api/projects` | projects.py | Admin |
| `/api/projects/{pid}/instances` | instances.py | API key |
| `/api/projects/{pid}/workspaces` | workspaces.py | API key |
| `/api/projects/{pid}/domains` | domains.py | API key |
| `/api/projects/{pid}/instances/{iid}/deploy` | deploy.py | API key |
| `/api/projects/{pid}/zar/{name}/...` | zar.py | API key |

### Zar Endpoints
- `POST .../zar/{name}/pack` — Pack workspace into .zar
- `POST .../zar/{name}/push` — Push .zar to R2
- `POST .../zar/{name}/deploy` — Deploy .zar to instance via agent
- `POST .../zar/{name}/ship` — Pack + push + deploy (all-in-one)
- `POST .../zar/{name}/rollback` — Rollback to previous snapshot
- `POST .../zar/{name}/branch` — Create branch from existing
- `POST .../zar/{name}/merge` — Copy latest from one branch to another
- `GET  .../zar/{name}/versions` — List versions/branches
- `POST .../zar/self-update` — Update agent/frontend/core on instance

## Agent Endpoints (port 8081)
- `POST /deploy/pull` — Download .zar from R2 and deploy
- `POST /deploy/upload` — Receive .zar via multipart
- `POST /deploy/rollback` — Restore previous snapshot
- `GET  /deploy/current` — Current deploy state
- `GET  /deploy/snapshots` — List snapshots
- `POST /deploy/self-update` — Update agent itself

## Environment Variables
See `.env.example`. Key vars:
- `VULTR_API_KEY` — Vultr API for VPS provisioning
- `CF_API_TOKEN` — Cloudflare for DNS
- `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` — R2 storage
- `AGENT_ADMIN_PASSWORD` — Password for agent JWT auth (used by zar deploy)
- `SETUPO_ADMIN_EMAIL` — Admin email

## Project Structure
```
setupo/
├── core/                    # Core business logic
│   ├── db.py               # SQLite persistence
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
│   ├── auth/               # JWT + API key middleware
│   └── routes/             # All API route handlers
├── nso-agent/             # VPS agent (runs on each instance)
│   ├── main.py             # Agent entry
│   ├── auth.py             # Agent-local JWT auth
│   ├── files.py            # File operations
│   ├── exec.py             # Command execution
│   ├── deploy.py           # .zar deploy/snapshot/rollback
│   ├── store.py            # SQLite metrics store
│   └── models.py           # Agent models
├── dashboard/               # Next.js admin dashboard
│   └── src/
├── deploy/                  # Production deploy configs
│   ├── bootstrap.sh        # Full Debian 12 VPS bootstrap
│   ├── nginx.conf          # Nginx reverse proxy config
│   ├── setupo.service      # Main API systemd unit
│   └── setupo-agent.service # Agent systemd unit
├── base/
│   ├── cloud-init.yaml     # VPS provisioning template
│   └── scripts/bootstrap.sh # Post-boot verification
├── .env.example
├── requirements.txt
└── PLAN.md                  # Feature planning document
```

## Common Commands
```bash
# Run API server (dev)
cd /opt/setupo && venv/bin/uvicorn server.main:app --reload --port 8000

# Run agent (dev)
cd /opt/setupo/nso-agent && ../venv/bin/uvicorn main:app --port 8081

# Build dashboard
cd dashboard && npm run build

# Pack a workspace
curl -X POST -H "Authorization: Bearer sk_live_xxx" \
  https://host/api/projects/{pid}/zar/{name}/pack

# Ship (pack + push + deploy)
curl -X POST -H "Authorization: Bearer sk_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"inst_xxx"}' \
  https://host/api/projects/{pid}/zar/{name}/ship
```
