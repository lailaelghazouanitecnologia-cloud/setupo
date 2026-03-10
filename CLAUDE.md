# NSO — Infrastructure Platform

## Infra

| Key | Value |
|-----|-------|
| Main VPS | 65.20.102.242 (nso.dev) |
| Test VPS | 65.20.103.88 |
| Provider | Vultr (VPS) + Cloudflare (DNS + R2) |
| DB | PostgreSQL 16 (central) / SQLite (agent) |

## Architecture

```
Central Server (:8000)          Agent (per VPS :8081)
nso/main.py (auto-discovery)    vm/agent/main.py
nso/engine/* (15 modules)       auth, files, exec, deploy, envvars
nso/shared/ (db, auth, deps)    SQLite metrics store

client/dashboard/ (Next.js)     vm/cli/ (Python CLI)
client/admin/ (Next.js)
```

### Nginx routing (nso.dev)
```
/api/*    → 127.0.0.1:8000  (central FastAPI)
/agent/*  → 127.0.0.1:8081  (nso-agent)
/ws/*     → WebSocket :8000
/         → static dashboard
```

## Auth

| Type | Format | Scope |
|------|--------|-------|
| Admin token | 64 random chars | Full access |
| User JWT | `usr_*.*.* ` (HS256) | User-scoped |
| API key | `sk_live_*` (SHA256) | Single project |
| Agent JWT | `*.*.*` (HS256) | Agent on VPS |

Dashboard uses two tokens: `nso_api_token` (central) + `nso_token` (agent).

## .zar Deploy System

```
pack workspace → push .zar to R2 → agent pulls → snapshot → extract → restart
```

R2 layout: `{project_id}/{workspace}/{branch}/v{version}.zar`

## Project Structure

```
setupo/
├── nso/                    # Central server
│   ├── main.py             # Auto-discovery (scans engine/*/config.toml)
│   ├── config.py           # Settings from env
│   ├── shared/             # db.py, auth/, deps.py, errors.py, ratelimit.py
│   └── engine/             # 15 modules, each has: config.toml, routes.py, service.py, migrations.py
│       ├── auth/           # Users, login, registration
│       ├── billing/        # Plans, subscriptions, wallets, invoices, Stripe
│       ├── compute/        # Instance CRUD, Vultr provider
│       ├── deploy/         # Deploy pipeline
│       ├── storage/        # R2 client, .zar pack/push
│       ├── workspace/      # Workspace config, files, sharing
│       ├── projects/       # Project CRUD
│       ├── dns/            # Domains, subdomains
│       ├── addons/         # Plugins, connectors, marketplace
│       ├── admin/          # Analytics, ledger, fraud
│       ├── notifications/  # Email, inbox
│       ├── orchestrator/   # Scheduler, pool, scaler, LB
│       └── secrets/        # Project env vars
├── vm/
│   ├── agent/              # NSO Agent (:8081) — auth, files, exec, deploy, envvars
│   ├── cli/                # Python CLI — main.py, client.py, output.py
│   └── nso                 # CLI entry point
├── client/
│   ├── dashboard/          # Main Next.js dashboard
│   └── admin/              # Admin Next.js dashboard
├── nso/base/               # Server setup scripts
│   ├── install.sh          # One-line installer (--central for PostgreSQL)
│   ├── setup-postgres.sh   # Standalone PostgreSQL setup
│   ├── migrate-sqlite-to-pg.py  # SQLite → PostgreSQL migration
│   └── cloud-init.yaml     # Cloud-init for user VPS instances
└── tests/
```

## Environment Variables

```bash
# Core
NSO_HOST=0.0.0.0
NSO_PORT=8000
NSO_JWT_SECRET=...          # REQUIRED in production
NSO_ADMIN_EMAIL=...
NSO_ADMIN_PASSWORD=...
AGENT_ADMIN_PASSWORD=...
DATABASE_URL=postgresql://nso:pass@localhost:5432/nso  # Central server only

# Vultr
VULTR_API_KEY=...

# Cloudflare
CF_API_TOKEN=...
CF_NSO_ZONE_ID=...
NSO_BASE_DOMAIN=nso.dev

# R2
R2_ENDPOINT=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=nso

# Stripe (optional)
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...

# Email (optional)
SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
```

## Commands

```bash
# Central server
cd /opt/nso && venv/bin/uvicorn nso.main:app --reload --port 8000

# Agent
cd /opt/nso/vm/agent && ../../venv/bin/uvicorn main:app --port 8081

# Dashboard
cd client/dashboard && npm run build

# Services
systemctl restart nso nso-agent

# Ship (all-in-one deploy)
nso ship my-workspace inst_xxx
```

## Tech Stack

Python 3.11+ / FastAPI / PostgreSQL (central) + SQLite (agent) / Cloudflare R2 / Next.js / Vultr / Stripe
