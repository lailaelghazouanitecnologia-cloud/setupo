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
│  ├── main.py       (entry, router mounting)                     │
│  ├── auth.py       (JWT login, PBKDF2)                          │
│  ├── files.py      (browse/read/write/delete)                   │
│  ├── exec.py       (command execution)                          │
│  ├── deploy.py     (pull .zar, snapshot, rollback, self-update) │
│  ├── envvars.py    (env var CRUD, bucket grouping)              │
│  ├── store.py      (SQLite metrics)                             │
│  └── models.py                                                  │
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
- **auth**: `NSO_ADMIN_*`, `AGENT_ADMIN_*`, `JWT_*`, `SECRET_*`
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
_modules/{name}/v{version}.zar          # System modules
_modules/{name}/latest.zar
```

### Deploy Flow
```
pack workspace → push .zar to R2 → agent pulls from R2 → snapshot → extract → restart
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
│   │   ├── main.py              # Agent entry
│   │   ├── auth.py              # Agent-local JWT auth
│   │   ├── files.py             # File operations (ALLOWED_ROOTS sandboxing)
│   │   ├── exec.py              # Command execution (blacklist-filtered)
│   │   ├── deploy.py            # .zar deploy/snapshot/rollback/self-update
│   │   ├── pipeline.py          # Multi-phase deploy pipeline (deploy.toml)
│   │   ├── supervisor.py        # Process supervisor with health checks
│   │   ├── pool_handler.py      # Pool VM handler (build nodes)
│   │   ├── ai.py                # AI deploy assistant
│   │   ├── envvars.py           # Env var CRUD with bucket grouping
│   │   ├── store.py             # SQLite metrics store
│   │   └── models.py            # Agent models
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
│   ├── install.sh               # One-line installer (--central for PostgreSQL mode)
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

# PostgreSQL setup (existing VPS)
bash nso/base/setup-postgres.sh --migrate /opt/nso/data/nso.db

# Fresh install (central server with PostgreSQL)
curl -fsSL https://nso.dev/install | bash -s -- --central --email admin@nso.dev
```

## VPS Directory Layout

```
/opt/nso/
├── config/
│   ├── agent.env           # Agent: JWT_SECRET, AGENT_ADMIN_PASSWORD, DATABASE_URL
│   └── nso.env             # Central: DATABASE_URL, provider keys
├── data/
│   └── nso.db              # SQLite (legacy/agent-only)
├── workspaces/             # Deployed workspace files
│   └── default/static/     # Default landing page
├── venv/                   # Python virtualenv (FastAPI, uvicorn, asyncpg, etc.)
├── vm/
│   ├── agent/              # Agent source
│   ├── cli/                # CLI source
│   └── nso                 # CLI binary
├── client/
│   ├── dashboard/static/   # Built dashboard (served by nginx)
│   └── admin/static/       # Built admin dashboard
└── repo/                   # Git clone of setupo (for updates)
```
