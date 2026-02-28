# Setupo — AI Agent Infrastructure Platform

## Infrastructure

| Detail | Value |
|--------|-------|
| Main VPS | 65.20.102.242 (nso.dev) |
| Test VPS | 65.20.103.88 |
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
│  ├── src/app/                  ├── main.py (entry + middleware) │
│  ├── src/components/           ├── config.py (env vars)         │
│  │   └── dashboard/            ├── deps.py (auth deps)          │
│  │       ├── admin-panel       ├── ratelimit.py (brute-force)   │
│  │       ├── billing-panel     ├── auth/                        │
│  │       ├── inbox-panel       │   ├── jwt.py (user JWT+PBKDF2) │
│  │       ├── instances-panel   │   ├── keys.py (sk_live_ gen)   │
│  │       ├── projects-panel    │   └── middleware.py (resolve)   │
│  │       ├── deploy-panel      └── routes/                      │
│  │       ├── secrets-panel         ├── health.py                │
│  │       ├── settings-panel        ├── auth.py (login+register) │
│  │       └── plugins-panel         ├── projects.py              │
│  ├── src/lib/api/client.ts         ├── instances.py             │
│  └── src/stores/                   ├── workspaces.py            │
│                                    ├── domains.py               │
│  core/                             ├── deploy.py                │
│  ├── db.py (SQLite + migrations)   ├── zar.py                   │
│  ├── models.py (Pydantic)          ├── plugins.py               │
│  ├── errors.py                     ├── billing.py (Stripe+plans)│
│  ├── workspace_config.py           ├── admin.py (user mgmt)     │
│  ├── users.py (user CRUD+auth)     ├── modules.py (sys modules) │
│  ├── billing.py (billing engine)   ├── notifications.py         │
│  ├── blockchain.py (ledger)        ├── subdomain.py             │
│  ├── analytics.py (metrics+fraud)  └── plugin_api.py            │
│  ├── email.py (SMTP+templates)                                  │
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
│  ├── envvars.py    (env var CRUD, bucket grouping)              │
│  ├── store.py      (SQLite metrics)                             │
│  └── models.py                                                  │
│                                                                 │
│  nginx → /api/ (:8000) + /agent/ (:8081) + / (static dashboard)│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   NSO CLIENT (Python CLI)                        │
│  cli/ — Python CLI (rich TUI)                                   │
│  Commands: nso login, nso ship, nso exec, nso inst              │
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

### Dependency injection (server/deps.py)

```python
require_project  → API key provides project_id; admin gets it from URL
require_admin    → Admin token or user with role="admin"
require_user     → User JWT (any authenticated user)
```

### Token resolution (server/auth/middleware.py)

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
    └── /           → /opt/setupo/dashboard/static (Next.js export)
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

### Plugin APIs (API key, requires plugin installed)
| Method | Path | Description |
|--------|------|-------------|
| GET | `.../p/storage/files` | List storage files (storage plugin) |
| POST | `.../p/storage/upload` | Upload file to R2 (storage plugin) |
| GET | `.../p/storage/download` | Download file (storage plugin) |
| DELETE | `.../p/storage/files` | Delete file (storage plugin) |
| GET | `.../p/logs` | Get deploy logs (logs plugin) |
| GET | `.../p/dns/records` | List DNS records (dns plugin) |
| POST | `.../p/dns/records` | Create DNS record (dns plugin) |
| DELETE | `.../p/dns/records/{id}` | Delete DNS record (dns plugin) |
| GET | `.../p/monitoring/instances` | Instance monitoring (monitoring plugin) |
| GET | `.../p/backups/list` | List .zar backups (backups plugin) |

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
| GET | `/api/billing/balance` | Legacy balance |
| GET | `/api/billing/transactions` | Legacy transactions |
| POST | `/api/billing/topup` | Admin balance top-up |
| POST | `/api/billing/charge` | Admin charge user |
| GET | `/api/billing/wallets` | List wallets |
| POST | `/api/billing/wallets` | Create wallet |
| GET | `/api/billing/wallets/{id}` | Get wallet |
| POST | `/api/billing/wallets/{id}/topup` | Top up wallet |
| GET | `/api/billing/wallets/{id}/transactions` | Wallet transactions |
| GET | `/api/billing/coupons` | List coupons (admin) |
| POST | `/api/billing/coupons` | Create coupon (admin) |
| POST | `/api/billing/coupons/{code}/deactivate` | Deactivate coupon (admin) |
| POST | `/api/billing/coupons/apply` | Apply coupon code |
| DELETE | `/api/billing/coupons/applied/{id}` | Remove applied coupon |
| GET | `/api/billing/coupons/applied` | List applied coupons |
| GET | `/api/billing/credit-notes` | List credit notes |
| POST | `/api/billing/credit-notes` | Create credit note (admin) |
| GET | `/api/billing/credit-notes/{id}` | Get credit note |
| POST | `/api/billing/credit-notes/{id}/void` | Void credit note (admin) |
| GET | `/api/billing/metrics` | List billable metrics (admin) |
| POST | `/api/billing/metrics` | Create metric (admin) |
| PATCH | `/api/billing/metrics/{code}` | Update metric (admin) |
| DELETE | `/api/billing/metrics/{code}` | Delete metric (admin) |
| POST | `/api/billing/usage` | Record usage event |
| GET | `/api/billing/usage/summary` | Usage summary for current period |
| GET | `/api/billing/taxes` | List tax rates (admin) |
| POST | `/api/billing/taxes` | Create tax rate (admin) |
| PATCH | `/api/billing/taxes/{code}` | Update tax rate (admin) |
| GET | `/api/billing/payment-methods` | List payment methods |
| DELETE | `/api/billing/payment-methods/{id}` | Remove payment method |
| POST | `/api/billing/payment-methods/{id}/default` | Set default |
| GET | `/api/billing/events` | List billing events (admin) |
| GET | `/api/billing/events/user` | User's billing events |
| GET | `/api/billing/overview` | Full billing overview |
| GET | `/api/billing/users` | Users with billing info (admin) |

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
| GET | `/api/admin/analytics/snapshots` | List snapshots |
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

### Core
| Table | Purpose |
|-------|---------|
| `projects` | Project metadata + API key hash |
| `instances` | VPS instances per project |
| `workspaces` | Workspace metadata per project |
| `domains` | Domain records per project |
| `deploy_logs` | Deploy log entries per instance |
| `plugins` | Installed plugins per project |
| `plugin_catalog` | Admin-published plugin definitions |
| `modules` | System module catalog (server, core, agent, dashboard) |

### Users & Auth
| Table | Purpose |
|-------|---------|
| `users` | User accounts (email, password_hash, role, balance, subdomain) |
| `email_tokens` | Single-use tokens for verification/reset |
| `notifications` | Per-user notification inbox |
| `activity_log` | User activity tracking + admin audit trail |
| `analytics_snapshots` | Periodic analytics snapshots |

### Billing (Lago-inspired)
| Table | Purpose |
|-------|---------|
| `billing_plans` | Plan definitions (code, interval, amount) |
| `billing_subscriptions` | Active subscriptions per user |
| `billing_invoices` | Invoice records |
| `billing_invoice_items` | Line items per invoice |
| `billing_payment_methods` | Stripe payment methods |
| `billing_usage_events` | Metered usage events |
| `billing_coupons` | Coupon definitions |
| `billing_applied_coupons` | Coupons applied to users |
| `billing_credit_notes` | Refunds and credits |
| `billing_billable_metrics` | Custom billing metrics |
| `billing_taxes` | Tax rate definitions |
| `billing_wallets` | Prepaid credit wallets |
| `billing_wallet_transactions` | Wallet transaction log |
| `billing_events` | Billing event audit trail |
| `transactions` | Legacy balance transactions |

### Blockchain Ledger
| Table | Purpose |
|-------|---------|
| `ledger_blocks` | Hash-linked transaction blocks per user |

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
SETUPO_HOST=0.0.0.0
SETUPO_PORT=8000
SETUPO_CORS_ORIGINS=https://nso.dev,http://localhost:3000
SETUPO_DATA_DIR=/opt/setupo/data
SETUPO_CONFIG_DIR=/opt/setupo/config
SETUPO_WORKSPACES_DIR=/opt/setupo/workspaces

# Admin
SETUPO_ADMIN_EMAIL=...
SETUPO_ADMIN_PASSWORD=...

# Agent
AGENT_ADMIN_PASSWORD=...
NSO_ADMIN_EMAIL=...

# JWT (auto-generated if not set — set in production for token persistence)
SETUPO_JWT_SECRET=...

# Email (optional — emails are no-op if not configured)
SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
SMTP_FROM=nso@nso.dev
SETUPO_EMAIL_SECRET=...           # auto-generated if not set

# Stripe (optional — for paid billing)
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_PUBLISHABLE_KEY=...
```

## Project Structure

```
setupo/
├── core/                    # Core business logic
│   ├── db.py               # SQLite persistence (aiosqlite) + migrations
│   ├── models.py           # All Pydantic models
│   ├── errors.py           # Exception hierarchy (SetupoError tree)
│   ├── workspace_config.py # config.toml reader/writer
│   ├── users.py            # User CRUD, auth, subdomain claiming
│   ├── billing.py          # Billing engine (plans, subs, invoices, wallets, Stripe)
│   ├── blockchain.py       # Immutable hash-linked ledger for financial traceability
│   ├── analytics.py        # Metrics, fraud detection, admin user management
│   ├── email.py            # SMTP email service (verification, reset, notifications)
│   ├── deploy/             # Deploy orchestration
│   │   ├── pipeline.py     # Deploy pipeline
│   │   └── sync.py         # File sync
│   ├── instances/          # Instance CRUD + lifecycle
│   │   ├── manager.py      # Instance management
│   │   ├── provisioner.py  # VPS provisioning
│   │   └── types.py        # Instance types
│   ├── projects/           # Project CRUD
│   │   └── manager.py      # Project management
│   ├── providers/          # Cloud provider clients
│   │   ├── base.py         # Provider base class
│   │   ├── vultr.py        # Vultr API client
│   │   └── cloudflare.py   # Cloudflare DNS + zone management
│   └── zar/                # .zar packaging system
│       ├── packer.py       # Pack/extract .zar archives
│       ├── storage.py      # R2 client (S3v4 HMAC signing, no boto3)
│       └── resolver.py     # Dependency resolution
├── server/                  # FastAPI HTTP layer
│   ├── main.py             # App entry, middleware stack, router mounting
│   ├── config.py           # Settings from env (all config centralized)
│   ├── deps.py             # Shared FastAPI dependencies (require_project/admin/user)
│   ├── ratelimit.py        # Rate limiting middleware (sliding window per IP)
│   ├── auth/               # Auth system
│   │   ├── jwt.py          # User JWT creation/decode + PBKDF2 password hashing
│   │   ├── keys.py         # API key generation (sk_live_)
│   │   └── middleware.py   # Token resolution (admin/user/API key) + AuthContext
│   └── routes/             # All API route handlers
│       ├── auth.py         # Login, register, profile, password reset, email verify
│       ├── health.py       # Health check
│       ├── projects.py     # Project CRUD
│       ├── instances.py    # Instance lifecycle
│       ├── workspaces.py   # Workspace management
│       ├── domains.py      # Domain management
│       ├── deploy.py       # Deploy orchestration
│       ├── zar.py          # .zar pack/push/deploy/ship
│       ├── plugins.py      # Plugin catalog (admin) + install (user)
│       ├── plugin_api.py   # Plugin runtime APIs (storage, logs, dns, monitoring, backups)
│       ├── billing.py      # Full billing API (plans, subs, checkout, invoices, wallets, coupons)
│       ├── admin.py        # Admin panel API (user mgmt, analytics, ledger, fraud)
│       ├── modules.py      # System module management (upload, catalog)
│       ├── notifications.py # Notification inbox CRUD
│       └── subdomain.py    # User subdomain claiming + DNS setup
├── nso-agent/               # VPS agent (runs on each instance)
│   ├── main.py             # Agent entry
│   ├── auth.py             # Agent-local JWT auth (PBKDF2)
│   ├── files.py            # File operations (browse/read/write/delete)
│   ├── exec.py             # Command execution
│   ├── deploy.py           # .zar deploy/snapshot/rollback
│   ├── envvars.py          # Env var CRUD with bucket grouping
│   ├── store.py            # SQLite metrics store
│   └── models.py           # Agent models
├── dashboard/               # Next.js admin dashboard
│   └── src/
│       ├── app/            # Next.js app router
│       │   ├── layout.tsx  # Root layout
│       │   ├── page.tsx    # Main page
│       │   └── global-error.tsx
│       ├── components/
│       │   └── dashboard/
│       │       ├── dashboard-layout.tsx  # Main layout + sidebar + header
│       │       ├── admin-panel.tsx       # Admin user management
│       │       ├── billing-panel.tsx     # Billing & subscription management
│       │       ├── inbox-panel.tsx       # Notifications
│       │       ├── instances-panel.tsx   # Instance management
│       │       ├── projects-panel.tsx    # Project + workspace management
│       │       ├── deploy-panel.tsx      # Deploy UI
│       │       ├── secrets-panel.tsx     # Secrets with bucket groups
│       │       ├── settings-panel.tsx    # User settings
│       │       └── plugins-panel.tsx     # Plugin catalog + install
│       ├── lib/
│       │   ├── api/client.ts            # API client (agent + central + billing)
│       │   └── utils.ts                 # Shared utilities
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
- **Payments**: Stripe (checkout, webhooks)
- **Email**: SMTP (verification, password reset, notifications)
- **Deploy**: cloud-init (bootstrap), systemd, nginx reverse proxy
- **CLI**: Python (rich, httpx)

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
  https://nso.dev/api/projects/{pid}/zar/{name}/ship

# Restart services
systemctl restart setupo setupo-agent
```
