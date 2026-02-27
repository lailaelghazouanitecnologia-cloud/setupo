# NSO — Platform Roadmap & Current State

## Current State (Feb 2026)

### Infrastructure
- **Main VPS**: 65.20.102.242 (zarnetti.com) — API + Agent + Dashboard
- **Test VPS**: 65.20.103.88 — Agent + Rust HTTP server on :3000
- **Provider**: Vultr (VPS), Cloudflare (DNS + R2 storage)
- **Project**: `proj_0f71067738c73681` (mesh-test)

### What Works

#### Core Platform
- Admin auth (JWT file-backed token) + project API keys (`sk_live_xxx`)
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
- Dual login (agent JWT + central admin token)
- Instance panel with terminal + file browser + labels
- Project panel with workspace management
- Deploy panel with instance/workspace selection
- **Secrets panel**: organized in collapsible buckets (auth, providers, storage, system, custom)
- **Plugins panel**: catalog browsing, install/uninstall, enable/disable
- **Header**: balance display, notification bell, support button, status indicator
- **Avatar menu**: API Keys, Notifications, Preferences, Logout

#### Plugin System
- **Admin catalog** (DB-backed): publish, update, unpublish, remove
- **User install**: browse published catalog, install per-project, enable/disable
- Auto-seeded with 6 default plugins (monitoring, backups, CI/CD, logs, DNS, cron)

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
- [x] Header: balance, notifications, support
- [x] Avatar menu: API Keys, Notifications, Preferences
- [x] Instance creation from dashboard

### Phase 4 — User Experience (next)
- [ ] Real-time instance updates (WebSocket or SSE instead of polling)
- [ ] Deploy logs streaming
- [ ] Workspace editor in dashboard
- [ ] "Download CLI" option in user dropdown
- [ ] User billing/balance system (backend)

### Phase 5 — NSO Client (Rust TUI)
- [ ] Rust binary with TUI (ratatui or similar)
- [ ] Auth: login, token storage
- [ ] Core commands: ship, exec, inst ls/create/rm
- [ ] Downloadable from dashboard
- [ ] Cross-platform builds (Linux, macOS, Windows)

### Phase 6 — Mesh Network (future)
- [ ] WireGuard overlay between NSO instances
- [ ] Service discovery via gossip protocol
- [ ] Encrypted P2P communication
- [ ] Central mesh coordinator on NSO Server

---

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, aiosqlite, httpx
- **Frontend**: Next.js (dashboard)
- **Database**: SQLite (async via aiosqlite)
- **Storage**: Cloudflare R2 (S3v4 HMAC signing, no boto3)
- **Providers**: Vultr (VPS), Cloudflare (DNS)
- **Deploy**: cloud-init (bootstrap), systemd, nginx reverse proxy
- **Future CLI**: Rust (tokio, ratatui)
