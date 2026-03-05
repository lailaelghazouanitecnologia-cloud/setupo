# NSO Restructuring Plan

## Current State — Diagnosis

```
setupo/                          PROBLEMS
├── server/     (~14,500 lines)  God objects (billing.py 1798L, db.py 832L)
│   ├── core/   (8,578 lines)   Single migration blob, no module boundaries
│   ├── routes/ (5,802 lines)   Routes mixed with business logic
│   └── auth/   (251 lines)     Scattered across server/auth + core/users
├── instance/   (3,229 lines)   Tightly coupled, no config.toml awareness
├── client/                      Broken React contexts, z86 mixed in
│   ├── dashboard/               static/ nested 5+ levels (build bug)
│   ├── admin/                   Minimal, likely broken imports
│   └── z86/                     Remove
├── cli/        (1,153 lines)   Works but no VM concept
├── z86/                         Out of scope — remove
├── common/                      Empty
├── doc/                         Scattered docs
├── scripts/                     Misc scripts
└── tests/      (1,162 lines)   5 files, poor coverage, low quality
```

Key issues:
- 11 root-level directories (should be 3)
- db.py has 673 lines of CREATE TABLE in a single string
- No module isolation — everything imports everything
- No workspace config.toml system for the platform itself
- No shareable workspace concept
- Tests are superficial — no property testing, no pipeline
- z86 references scattered in server/routes, client, root

---

## Target State — Architecture

```
setupo/
├── vm/                          # VM runtime + CLI
│   ├── cli/                     # nso CLI commands
│   │   ├── main.py              # entry point + arg parser
│   │   ├── client.py            # HTTP client
│   │   └── output.py            # terminal formatting
│   ├── agent/                   # per-VPS agent (:8081)
│   │   ├── main.py              # agent entry
│   │   ├── auth.py              # agent JWT
│   │   ├── files.py             # file CRUD
│   │   ├── exec.py              # command execution
│   │   ├── deploy.py            # .zar deploy/snapshot/rollback
│   │   ├── envvars.py           # env var management
│   │   ├── pipeline.py          # build pipelines
│   │   ├── healthcheck.py       # health reporting
│   │   └── store.py             # SQLite metrics
│   ├── config.toml              # VM workspace config
│   └── nso                      # CLI entry point script
│
├── nso/                         # Core platform (central server :8000)
│   ├── main.py                  # FastAPI app entry, module registration
│   ├── config.py                # env-based settings
│   ├── shared/                  # Shared infrastructure
│   │   ├── db.py                # Database connection + generic CRUD
│   │   ├── models.py            # Shared Pydantic models
│   │   ├── errors.py            # Exception hierarchy
│   │   ├── middleware.py        # CORS, rate limit, admin host
│   │   └── auth/                # Token resolution
│   │       ├── jwt.py           # JWT + PBKDF2
│   │       ├── keys.py          # API key generation
│   │       └── resolve.py       # Token → AuthContext
│   ├── engine/                  # Business logic modules (microvms)
│   │   ├── auth/                # Auth microvm
│   │   │   ├── service.py       # user CRUD, login, register
│   │   │   ├── routes.py        # /api/auth/*
│   │   │   ├── models.py        # auth-specific types
│   │   │   ├── migrations.py    # users, email_tokens tables
│   │   │   └── config.toml      # module config
│   │   ├── billing/             # Billing microvm
│   │   │   ├── service.py       # billing engine (split from 1798L)
│   │   │   ├── plans.py         # plan management
│   │   │   ├── invoices.py      # invoice logic
│   │   │   ├── wallets.py       # wallet management
│   │   │   ├── coupons.py       # coupon logic
│   │   │   ├── usage.py         # metered usage
│   │   │   ├── stripe.py        # Stripe integration
│   │   │   ├── routes.py        # /api/billing/*
│   │   │   ├── models.py        # billing types
│   │   │   ├── migrations.py    # billing_* tables
│   │   │   └── config.toml
│   │   ├── compute/             # Instance management microvm
│   │   │   ├── service.py       # instance lifecycle
│   │   │   ├── provisioner.py   # VPS provisioning (Vultr)
│   │   │   ├── routes.py        # /api/projects/{pid}/instances/*
│   │   │   ├── models.py
│   │   │   ├── migrations.py    # instances table
│   │   │   └── config.toml
│   │   ├── storage/             # R2 + .zar storage microvm
│   │   │   ├── service.py       # R2 operations
│   │   │   ├── zar_packer.py    # .zar pack/unpack
│   │   │   ├── zar_resolver.py  # dependency resolution
│   │   │   ├── routes.py        # /api/projects/{pid}/zar/*
│   │   │   ├── models.py
│   │   │   ├── migrations.py
│   │   │   └── config.toml
│   │   ├── deploy/              # Deploy pipeline microvm
│   │   │   ├── service.py       # deploy orchestration
│   │   │   ├── sync.py          # agent communication
│   │   │   ├── routes.py        # deploy endpoints
│   │   │   ├── models.py
│   │   │   ├── migrations.py    # deploy_logs table
│   │   │   └── config.toml
│   │   ├── workspace/           # Workspace management microvm
│   │   │   ├── service.py       # workspace CRUD
│   │   │   ├── config.py        # config.toml reader/writer
│   │   │   ├── share.py         # workspace sharing (join codes)
│   │   │   ├── nesting.py       # nested workspace resolution
│   │   │   ├── routes.py        # /api/projects/{pid}/workspaces/*
│   │   │   ├── models.py
│   │   │   ├── migrations.py    # workspaces, workspace_shares tables
│   │   │   └── config.toml
│   │   ├── projects/            # Project management microvm
│   │   │   ├── service.py       # project CRUD
│   │   │   ├── routes.py        # /api/projects/*
│   │   │   ├── models.py
│   │   │   ├── migrations.py    # projects table
│   │   │   └── config.toml
│   │   ├── dns/                 # Domain management microvm
│   │   │   ├── service.py       # Cloudflare DNS ops
│   │   │   ├── routes.py        # /api/projects/{pid}/domains/*
│   │   │   ├── models.py
│   │   │   ├── migrations.py    # domains table
│   │   │   └── config.toml
│   │   ├── addons/              # Addon/plugin system microvm
│   │   │   ├── service.py       # addon lifecycle
│   │   │   ├── catalog.py       # catalog management
│   │   │   ├── routes.py        # /api/projects/{pid}/addons/*
│   │   │   ├── models.py
│   │   │   ├── migrations.py
│   │   │   └── config.toml
│   │   ├── admin/               # Admin panel microvm
│   │   │   ├── service.py       # admin operations
│   │   │   ├── analytics.py     # metrics, fraud detection
│   │   │   ├── ledger.py        # blockchain ledger
│   │   │   ├── routes.py        # /api/admin/*
│   │   │   ├── models.py
│   │   │   ├── migrations.py    # activity_log, analytics_snapshots
│   │   │   └── config.toml
│   │   ├── notifications/       # Notification microvm
│   │   │   ├── service.py       # notification + email
│   │   │   ├── routes.py
│   │   │   ├── models.py
│   │   │   ├── migrations.py    # notifications table
│   │   │   └── config.toml
│   │   └── orchestrator/        # Orchestrator + LB microvm
│   │       ├── scheduler.py     # build scheduling
│   │       ├── monitor.py       # health monitoring
│   │       ├── scaler.py        # auto-scaling
│   │       ├── loadbalancer.py  # LB pool management
│   │       ├── routes.py        # /api/admin/orchestrator/*, /api/admin/lb/*
│   │       ├── models.py
│   │       ├── migrations.py    # instance_pool, build_queue, lb_*
│   │       └── config.toml
│   └── config.toml              # Platform workspace config
│
├── client/                      # Frontend dashboards
│   ├── dashboard/               # Main user dashboard (Next.js)
│   │   ├── src/
│   │   │   ├── app/             # Next.js app router
│   │   │   ├── components/      # UI components (by feature)
│   │   │   │   ├── auth/        # login, register
│   │   │   │   ├── billing/     # billing panel
│   │   │   │   ├── compute/     # instances panel
│   │   │   │   ├── deploy/      # deploy panel
│   │   │   │   ├── workspace/   # workspace panel
│   │   │   │   ├── settings/    # settings panel
│   │   │   │   └── shared/      # layout, nav, common UI
│   │   │   ├── lib/
│   │   │   │   └── api/         # API client (typed)
│   │   │   ├── stores/          # Zustand stores (one per feature)
│   │   │   └── types/           # TypeScript types
│   │   ├── package.json
│   │   └── config.toml          # Dashboard workspace config
│   └── admin/                   # Admin dashboard (Next.js)
│       ├── src/
│       ├── package.json
│       └── config.toml
│
├── config.toml                  # Root workspace config (meta)
├── requirements.txt
├── pytest.ini
├── .gitignore
└── CLAUDE.md
```

---

## Design Decisions

### 1. Module Registration (Hybrid MicroVM)

Each engine module is self-contained and auto-registers via config.toml:

```toml
# nso/engine/auth/config.toml
[workspace]
name = "auth"
version = "0.1.0"

[workspace.dependencies]
shared = { path = "../../shared" }

[workspace.routes]
prefix = "/api/auth"
tags = ["auth"]
```

```python
# nso/main.py discovers modules from engine/*/config.toml
# Each module owns: routes, service, models, migrations, config
# Modules communicate via explicit imports, never globals
# Split to processes later: replace imports with HTTP calls
```

### 2. Per-Module Migrations

Each module owns its tables. db.py discovers and runs them all:

```python
# nso/engine/auth/migrations.py
TABLES = """
    CREATE TABLE IF NOT EXISTS users (...);
    CREATE TABLE IF NOT EXISTS email_tokens (...);
"""
INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
"""
```

### 3. Workspace Config (config.toml everywhere)

Every directory that is a workspace has config.toml.
Admin nests workspaces via [workspace.children].
Dependencies declared explicitly.

### 4. Shareable Workspaces (Join Codes)

```
POST /api/projects/{pid}/workspaces/{name}/share
→ { "join_code": "ws_j_a1b2c3d4", "join_url": "https://nso.dev/join/ws_j_a1b2c3d4" }

GET /api/join/{code}
→ grants access based on permissions in workspace_shares table
```

### 5. Testing Strategy

- Property-based testing with hypothesis
- Test positive AND negative space
- Pipeline tests for end-to-end flows
- Each module has its own test file

---

## Execution Phases

### Phase 1 — Clean (remove z86, create folders)
1. Remove z86/, client/z86/, server/routes/z86_storage.py, z86 refs
2. Create vm/, nso/, client/ structure
3. Create config.toml files
4. Move CLI + agent into vm/

### Phase 2 — Split Server into Modules
5. Create nso/shared/ from server/core/db.py, models.py, errors.py
6. Create nso/shared/auth/ from server/auth/
7. Split core/ + routes/ into engine modules (12 modules)

### Phase 3 — Per-module Migrations
8. Extract CREATE TABLE into per-module migrations.py
9. Update db.py for module discovery
10. Validate all tables exist

### Phase 4 — Workspace Sharing
11. Implement share service (join codes)
12. Nested workspace resolution
13. Share/join routes

### Phase 5 — Fix Frontend
14. Remove client/z86/
15. Fix dashboard React contexts
16. Reorganize components by feature
17. Fix static/ nesting, add .gitignore
18. Fix admin/ imports

### Phase 6 — Testing
19. Add hypothesis
20. Property tests for billing, zar, auth
21. Integration tests for API flows
22. Pipeline tests for deploy + workspace share

### Phase 7 — Cleanup
23. Update CLAUDE.md
24. Remove dead files (common/, scripts/, doc/)
25. Update requirements.txt + imports
26. Final validation
