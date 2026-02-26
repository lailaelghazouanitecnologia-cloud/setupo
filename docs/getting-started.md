# Getting Started with NSO

## What is NSO?

NSO (Network Service Orchestration) is an infrastructure platform that provisions VPS instances, deploys code, and manages everything via API or CLI. No SSH between you and your servers — an agent on each VPS handles everything over HTTP.

**Live**: `https://zarnetti.com` — Madrid, Debian 12, 4vCPU/8GB

## Architecture

```
You (CLI/API) ──HTTPS──► NSO API (:8000) ──HTTP──► Agent (:8081) on VPS
                          │                         │
                          ├── Dashboard (/)          ├── /files (browse/edit)
                          ├── /api/health            ├── /exec (run commands)
                          ├── /api/projects          ├── /deploy (zar/rollback)
                          └── /api/zar/*             └── /auth (JWT login)
                                │
                                └── R2 (Cloudflare) ← .zar packages
```

## Quick Start

### 1. Install (local development)

```bash
git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git
cd setupo
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your keys
```

### 2. Start the server

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8000
# → Running on http://localhost:8000
```

### 3. Login with the CLI

```bash
./nso config host https://zarnetti.com  # or localhost:8000
./nso login -e ayman_gha@hotmail.com
./nso status
```

### 4. Create a project

```bash
./nso projects create my-saas
# OK Project: proj_a1b2c3
# > API key: sk_live_x9f3k2m...
# WARN Save this — won't be shown again

export NSO_PROJECT=proj_a1b2c3
./nso login -k sk_live_x9f3k2m...
```

### 5. Create a VPS instance

```bash
./nso inst create prod-1 --domain app.mysite.com --plan vc2-1c-2gb
# > Creating 'prod-1'...
#   1-3 min (VPS + cloud-init)
# OK Instance: inst_m3n4o5
#   IP        149.28.xx.xx
#   Status    provisioning

./nso inst status inst_m3n4o5
```

### 6. Deploy

```bash
./nso ws create backend --type python
# Put your code in workspaces/backend/

./nso ship backend inst_m3n4o5
# > Shipping 'backend' → inst_m3n4o5
#   pack → push R2 → snapshot → extract → restart
# OK Shipped in 12.3s
```

### 7. Something wrong? Rollback

```bash
./nso rollback backend inst_m3n4o5
# OK Restored: backend_20260226_143012.tar.gz
```

## Auth Methods

| Method | Access | Use case |
|--------|--------|----------|
| Admin login (`-e`) | All projects | Administration |
| API key (`-k sk_live_...`) | Single project | CI/CD, automation |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `NSO_HOST` | API server URL |
| `NSO_TOKEN` | Auth token |
| `NSO_PROJECT` | Default project ID |
| `NSO_ADMIN_EMAIL` | Agent admin email |
| `AGENT_ADMIN_PASSWORD` | Agent password (for exec) |

## Live URLs

| URL | What |
|-----|------|
| `https://zarnetti.com/` | Dashboard (login required) |
| `https://zarnetti.com/api/health` | API health check |
| `https://zarnetti.com/agent/health` | Agent health check |
| `https://zarnetti.com/docs` | Swagger UI (interactive API docs) |
| `https://zarnetti.com/openapi.json` | OpenAPI spec |

## Services on VPS

| Service | Port | Systemd unit | Purpose |
|---------|------|-------------|---------|
| NSO API | 8000 | `setupo.service` | Central API (FastAPI + uvicorn) |
| NSO Agent | 8081 | `setupo-agent.service` | VPS management (files, exec, deploy) |
| Nginx | 80 | `nginx.service` | Reverse proxy + static dashboard |

## Tech Stack

- **Backend**: Python 3.11, FastAPI, aiosqlite, httpx
- **Dashboard**: Next.js 15, React 19, Tailwind 4, static export
- **Storage**: Cloudflare R2 (S3v4 signing, no boto3)
- **Providers**: Vultr (VPS), Cloudflare (DNS + R2)
- **OS**: Debian 12 (bookworm), 4vCPU minimum
- **Deploy**: cloud-init bootstrap, .zar packages, snapshot rollback

## Next Steps

- [CLI Reference](cli.md)
- [API Reference](api-reference.md) — All 34 endpoints
- [Failure Recovery](failure-recovery.md) — What can go wrong and how to fix it
- [SKILL.md](../SKILL.md) — AI agent skill documentation
