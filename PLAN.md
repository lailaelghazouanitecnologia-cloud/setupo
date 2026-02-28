# NSO — Platform Roadmap & Current State

## Current State (Feb 2026)

### Infrastructure
- **Main VPS**: 65.20.102.242 (nso.dev) — API + Agent + Dashboard
- **Test VPS**: 65.20.103.88 — Agent
- **Provider**: Vultr (VPS), Cloudflare (DNS + R2 storage)
- **Domain**: nso.dev (user subdomains: username.project.nso.dev)
- **Project**: `proj_0f71067738c73681` (mesh-test)

### What Works

#### Core Platform
- **Admin auth** (JWT file-backed token) + project API keys (`sk_live_xxx`)
- **User auth** (register/login with JWT `usr_xxx` tokens)
- Project CRUD + API key rotation
- Instance lifecycle: create, start, stop, destroy (Vultr)
- Workspace management: create, list, deploy, file editing
- .zar packaging: pack → push to R2 → agent pulls → snapshot → extract → restart
- Branch/version system for .zar packages
- cloud-init provisioning for new VPS instances
- Exec commands on instances via HTTP relay (no SSH)

#### Agent (nso-agent/)
- File operations: browse, read, write, delete, tree
- Command execution + systemd service management
- Deploy: pull .zar from R2, snapshot, rollback, self-update
- **Secrets management**: CRUD via API (no shell commands), bucket grouping
- Installation metrics tracking

#### Dashboard
- **Landing page**: public marketing page with feature highlights
- **Login + Register**: user account creation, admin & user login
- Instance panel with terminal + file browser + labels
- Project panel with workspace management
- Deploy panel with instance/workspace selection
- **Secrets panel**: organized in collapsible buckets (auth, providers, storage, system, custom)
- **Plugins panel**: catalog browsing, install/uninstall, enable/disable
- **Header**: balance display, notification bell
- **Avatar menu**: API Keys, Notifications, Preferences, Logout

#### Billing System (simulated)
- User balance tracking
- Top-up (simulated payment)
- Transaction history (charges, top-ups)
- Admin: charge users, list all users

#### Plugin System
- **Admin catalog** (DB-backed): publish, update, unpublish, remove
- **User install**: browse published catalog, install per-project, enable/disable
- Auto-seeded with 6 default plugins (monitoring, backups, CI/CD, logs, DNS, cron)

#### Module Marketplace (.zar)
- Platform modules (server, core, nso-agent, dashboard) as .zar packages
- Admin publishes module versions to R2
- Public catalog browse
- Auto-seeded with 4 core modules

#### Deploy Error Handling
- Agent httpx calls wrapped with try/except
- Instance state validation before deploy
- Frontend strips HTML from Cloudflare error pages
- Client-side instance state checking

---

## Roadmap

### Phase 1 — Stabilize & Clean ✅
- [x] Fix admin auth on project-scoped endpoints
- [x] Dashboard auto-load instances + terminal + files
- [x] Instance labels
- [x] Move admin credentials to env vars
- [x] Unify password hashing (PBKDF2 everywhere)
- [x] Update .env.example with all agent vars

### Phase 2 — Rename & Reorganize ✅
- [x] Rename `mms-metrics/` → `nso-agent/`
- [x] Update all references (systemd, nginx, deploy scripts, cloud-init)
- [x] Add proper error handling for agent HTTP relay
- [x] Deploy error handling + state validation

### Phase 3 — Dashboard + Plugins + Secrets ✅
- [x] Plugin system: DB-backed catalog + admin management + user install
- [x] Secrets: agent API (no shell), bucket grouping, collapsible UI
- [x] Header: balance, notifications
- [x] Avatar menu: API Keys, Notifications, Preferences
- [x] Instance creation from dashboard

### Phase 4 — Users + Billing + Marketplace ✅
- [x] User registration + login (JWT `usr_xxx` tokens)
- [x] Landing page + login + register UI
- [x] Billing system (balance, top-up, charges, transactions)
- [x] Module marketplace (.zar modules in R2)
- [x] Domain change: zarnetti.com → nso.dev
- [x] Free subdomains: username.project.nso.dev

### Phase 5 — User Experience (next)
- [ ] Real-time instance updates (WebSocket or SSE instead of polling)
- [ ] Deploy logs streaming
- [ ] Workspace editor in dashboard
- [ ] "Download CLI" option in user dropdown
- [ ] User dashboard (billing panel, module browser, project management)

### Phase 6 — NSO Client (Python CLI) ✅
- [x] Python CLI with rich TUI
- [x] Auth: login, token storage
- [x] Core commands: ship, exec, inst ls/create/rm, versions, branch, merge
- [ ] Downloadable from dashboard
- [ ] Package as standalone binary (PyInstaller)

### Phase 7 — Mesh Network (future)
- [ ] WireGuard overlay between NSO instances
- [ ] Service discovery via gossip protocol
- [ ] Encrypted P2P communication
- [ ] Central mesh coordinator on NSO Server

---

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, aiosqlite, httpx
- **Frontend**: Next.js (dashboard + landing page)
- **Database**: SQLite (async via aiosqlite)
- **Storage**: Cloudflare R2 (S3v4 HMAC signing, no boto3)
- **Providers**: Vultr (VPS), Cloudflare (DNS)
- **Deploy**: cloud-init (bootstrap), systemd, nginx reverse proxy
- **CLI**: Python (rich, httpx)
