# NSO Skill — AI Agent Infrastructure Management

This document teaches AI agents how to use the NSO platform to manage infrastructure.

## What is NSO?

NSO is an infrastructure platform. You can:
- Create VPS instances on Vultr
- Deploy code to instances via .zar packages (no SSH to our servers)
- Execute commands on instances via HTTP agent
- From instances, SSH or curl to external systems
- Manage DNS via Cloudflare
- Rollback deployments instantly

## Core Concepts

### Two-Level Architecture

```
Level 1: You → NSO API → Agent on VPS (HTTP, no SSH)
Level 2: Agent on VPS → External systems (SSH, curl, anything)
```

You never SSH into NSO instances directly. The agent handles everything.
But FROM an NSO instance, you CAN SSH to external systems via `nso exec`.

### .zar Packages

A `.zar` is a compressed workspace archive (tar.gz) containing code, config, and manifest.
Stored in Cloudflare R2. Deployed to instances via the agent.

### Snapshots

Before every deploy, a snapshot of the current state is taken.
If deploy fails → automatic rollback. Max 5 snapshots per target.

## CLI Commands

### Authentication

```bash
# Login with admin credentials
nso login -e admin@example.com

# Login with project API key
nso login -k sk_live_abc123

# Set API host
nso config host https://zarnetti.com

# Check status
nso status
```

### Projects

```bash
# Create a project (returns API key)
nso projects create my-project

# List projects
nso projects ls

# Delete (destroys all instances)
nso projects rm proj_xxx -f
```

### Instances (VPS)

```bash
# Set project context
export NSO_PROJECT=proj_xxx

# Create VPS
nso inst create prod-server --domain app.mysite.com --plan vc2-1c-2gb

# List
nso inst ls

# Status
nso inst status inst_xxx

# Destroy
nso inst rm inst_xxx -f
```

### Deploy

```bash
# Ship = pack + upload to R2 + deploy to instance (recommended)
nso ship my-workspace inst_xxx

# With version/branch
nso ship my-workspace inst_xxx -v 2.0.0 -b staging

# Just pack (no upload, no deploy)
nso pack my-workspace

# Just upload to R2
nso push my-workspace

# Deploy from R2 (already uploaded)
nso deploy my-workspace inst_xxx

# Rollback to previous version
nso rollback my-workspace inst_xxx
```

### Branching

```bash
# Create branch from main
nso branch my-workspace staging

# Ship to staging branch
nso ship my-workspace inst_test -b staging

# Merge staging into main
nso merge my-workspace staging main

# List versions
nso versions my-workspace
```

### Execute Commands

```bash
# Run command on instance (via agent HTTP, not SSH)
nso exec inst_xxx ls -la /opt/app
nso exec inst_xxx systemctl status myapp
nso exec inst_xxx cat /var/log/myapp.log

# From instance, reach external systems
nso exec inst_xxx ssh user@external-server uptime
nso exec inst_xxx curl https://api.external.com/health
nso exec inst_xxx scp file.txt user@external:/tmp/
```

### Self-Update

```bash
# Update the agent on the instance (no VPS recreation)
nso update inst_xxx --target agent

# Update the dashboard
nso update inst_xxx --target frontend

# Update the core API
nso update inst_xxx --target core
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `NSO_HOST` | API server URL |
| `NSO_TOKEN` | Auth token |
| `NSO_PROJECT` | Default project ID |
| `NSO_ADMIN_EMAIL` | Agent admin email |
| `AGENT_ADMIN_PASSWORD` | Agent password |

## Deploy Flow (What Happens Internally)

When you run `nso ship workspace instance`:

1. **Pack**: Workspace directory → .zar archive (excludes .git, node_modules, .env)
2. **Push**: .zar uploaded to Cloudflare R2 with version key
3. **Agent Login**: API authenticates with the agent on the target VPS
4. **Snapshot**: Agent creates tar.gz backup of current app state
5. **Download**: Agent downloads .zar from R2 (verifies SHA-256 hash)
6. **Extract**: .zar extracted to target directory (preserves .env)
7. **Install**: pip install / npm install if requirements found
8. **Restart**: systemctl restart the service
9. **Verify**: Health check — if fails, auto-rollback to snapshot

## Failure Handling

| Failure | What happens |
|---------|-------------|
| Extraction fails | Auto-rollback to snapshot |
| Service won't start | Auto-rollback to snapshot |
| R2 download fails | Nothing modified, retry safe |
| Hash mismatch | Abort before extraction |
| Disk full | Snapshot fails → deploy aborted |
| Concurrent deploy | Second deploy rejected (lock) |
| Agent dies during self-update | systemd auto-restarts |
| API dies during core update | Agent still runs on :8081 |

## Common Workflows

### Deploy to production

```bash
export NSO_PROJECT=proj_xxx

# Test on staging first
nso branch backend staging
nso ship backend inst_staging -b staging

# Verify
nso exec inst_staging curl -s localhost:3000/health

# Merge and deploy to production
nso merge backend staging main
nso ship backend inst_prod
```

### Recover from bad deploy

```bash
# Automatic: ship already rolled back
# Manual:
nso rollback backend inst_prod

# Check what went wrong
nso exec inst_prod journalctl -u setupo-app -n 50
```

### Update infrastructure without downtime

```bash
# Update agent
nso update inst_prod --target agent

# Update API
nso update inst_prod --target core

# Update dashboard
nso update inst_prod --target frontend
```

### Run commands on external systems via instance

```bash
# The instance is YOUR proxy to external systems
nso exec inst_xxx ssh deploy@production-db "pg_dump mydb > /tmp/backup.sql"
nso exec inst_xxx scp deploy@production-db:/tmp/backup.sql /opt/backups/
nso exec inst_xxx curl -X POST https://slack.com/api/chat.postMessage -d "Deploy complete"
```

## API Endpoints (for programmatic access)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/login` | Get JWT token |
| GET | `/api/health` | Health check |
| GET/POST/DELETE | `/api/projects` | Project CRUD |
| GET/POST/DELETE | `/api/projects/{pid}/instances` | Instance CRUD |
| GET/POST | `/api/projects/{pid}/workspaces` | Workspace CRUD |
| POST | `/api/projects/{pid}/zar/{name}/ship` | Ship (all-in-one) |
| POST | `/api/projects/{pid}/zar/{name}/deploy` | Deploy from R2 |
| POST | `/api/projects/{pid}/zar/{name}/rollback` | Rollback |
| POST | `/api/projects/{pid}/zar/{name}/pack` | Pack only |
| POST | `/api/projects/{pid}/zar/{name}/push` | Push to R2 |
| POST | `/api/projects/{pid}/zar/{name}/branch` | Create branch |
| POST | `/api/projects/{pid}/zar/{name}/merge` | Merge branches |
| GET | `/api/projects/{pid}/zar/{name}/versions` | List versions |
| POST | `/api/projects/{pid}/zar/self-update` | Update component |

All endpoints accept `Authorization: Bearer <token>` header.
