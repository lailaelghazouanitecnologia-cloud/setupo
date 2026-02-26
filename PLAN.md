# NSO — Platform Roadmap & Current State

## Current State (Feb 2026)

### Infrastructure
- **Main VPS**: 65.20.102.242 (zarnetti.com) — API + Agent + Dashboard
- **Test VPS**: 65.20.103.88 — Agent + Rust HTTP server on :3000
- **Provider**: Vultr (VPS), Cloudflare (DNS + R2 storage)
- **Project**: `proj_0f71067738c73681` (mesh-test)

### What Works
- Admin auth (JWT) + project API keys (`sk_live_xxx`)
- Project CRUD + API key rotation
- Instance lifecycle: create, start, stop, destroy (Vultr)
- Workspace management: create, list, deploy
- .zar packaging: pack → push to R2 → agent pulls → snapshot → extract → restart
- Branch/version system for .zar packages
- Dashboard: login, project management, instance panel with terminal + files
- Agent (nso-agent): file ops, exec, deploy/snapshot/rollback, self-update
- cloud-init provisioning for new VPS instances
- Exec commands on instances via HTTP relay (no SSH from central)

### Known Issues
- Dashboard instance terminal uses central API exec relay (latency), not direct agent connection

---

## Architecture: Three Layers of NSO

```
┌──────────────────────────────────────────────────────┐
│  NSO Server (Central)                                │
│  FastAPI :8000 + Next.js Dashboard                   │
│  Manages: projects, instances, workspaces, deploys   │
│  Storage: SQLite + Cloudflare R2                     │
└──────────────┬───────────────────────────────────────┘
               │ HTTP (no SSH)
               ▼
┌──────────────────────────────────────────────────────┐
│  NSO Agent (per VPS instance)                        │
│  FastAPI :8081 (nso-agent/)                           │
│  Handles: file ops, exec, deploy, snapshots,         │
│           rollback, self-update                      │
│  Auth: JWT (PBKDF2 password)                         │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  NSO Client (future)                                 │
│  Rust TUI binary — downloadable from dashboard       │
│  Commands: nso login, nso ship, nso exec, nso inst   │
│  Replaces curl-based API usage                       │
└──────────────────────────────────────────────────────┘
```

---

## Roadmap

### Phase 1 — Stabilize & Clean (current)
- [x] Fix admin auth on project-scoped endpoints
- [x] Dashboard auto-load instances + terminal + files
- [x] Instance labels
- [x] Move admin credentials to env vars (remove hardcoded ADMIN_USERS)
- [x] Unify password hashing (PBKDF2 everywhere)
- [x] Update .env.example with all agent vars
- [x] Clean obsolete docs (PLAN.md rewritten)

### Phase 2 — Rename & Reorganize
- [x] Rename `mms-metrics/` → `nso-agent/`
- [x] Update all references (systemd, nginx, deploy scripts, cloud-init)
- [ ] Consolidate deploy configs
- [ ] Add proper error handling for agent HTTP relay

### Phase 3 — Dashboard Improvements
- [ ] Real-time instance updates (WebSocket or SSE instead of polling)
- [ ] "Download CLI" option in user dropdown
- [ ] Workspace editor in dashboard
- [ ] Deploy logs streaming

### Phase 4 — NSO Client (Rust TUI)
- [ ] Rust binary with TUI (ratatui or similar)
- [ ] Auth: login, token storage
- [ ] Core commands: ship, exec, inst ls/create/rm
- [ ] Downloadable from dashboard
- [ ] Cross-platform builds (Linux, macOS, Windows)

### Phase 5 — Mesh Network (future)
- [ ] WireGuard overlay between NSO instances
- [ ] Service discovery via gossip protocol
- [ ] Encrypted P2P communication
- [ ] Central mesh coordinator on NSO Server

---

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, aiosqlite, httpx
- **Frontend**: Next.js (dashboard), Tailwind CSS, shadcn/ui
- **Database**: SQLite (async via aiosqlite)
- **Storage**: Cloudflare R2 (S3v4 HMAC signing, no boto3)
- **Providers**: Vultr (VPS), Cloudflare (DNS)
- **Deploy**: cloud-init (bootstrap), systemd, nginx reverse proxy
- **Future CLI**: Rust (tokio, ratatui)
