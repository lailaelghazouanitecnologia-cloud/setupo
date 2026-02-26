# Setupo API Reference

Base URL: `https://your-server.com` (port 8000)

## Authentication

### Login (Admin)

```
POST /api/auth/login
```

```json
{
  "email": "admin@example.com",
  "password": "your-password"
}
```

Response:
```json
{
  "token": "eyJhbGciOi...",
  "email": "admin@example.com"
}
```

### Using Auth

All protected endpoints accept:
- **Admin JWT**: `Authorization: Bearer eyJhbG...`
- **Project API key**: `Authorization: Bearer sk_live_abc123`

API keys are scoped to a single project and can only access that project's resources.

---

## Health

### Check API Health

```
GET /api/health
```

No auth required.

Response:
```json
{
  "status": "ok",
  "capabilities": {
    "version": "0.2.0",
    "actions": ["workspaces.pack", "workspaces.deploy", ...]
  }
}
```

---

## Projects

### List Projects

```
GET /api/projects
```

Auth: Admin only.

### Create Project

```
POST /api/projects
```

```json
{
  "name": "my-saas"
}
```

Response includes a one-time API key:
```json
{
  "id": "proj_a1b2c3",
  "name": "my-saas",
  "api_key": "sk_live_x9f3k2m...",
  "created_at": "2026-02-26T14:30:00Z"
}
```

### Delete Project

```
DELETE /api/projects/{project_id}
```

Destroys all instances and workspaces.

---

## Instances

All instance endpoints require project-scoped auth.

### List Instances

```
GET /api/projects/{project_id}/instances
```

### Create Instance

```
POST /api/projects/{project_id}/instances
```

```json
{
  "label": "prod-1",
  "region": "ewr",
  "plan": "vc2-1c-2gb",
  "domain": "app.mysite.com"
}
```

Response:
```json
{
  "id": "inst_m3n4o5",
  "label": "prod-1",
  "ip": "149.28.xx.xx",
  "status": "provisioning",
  "region": "ewr",
  "plan": "vc2-1c-2gb"
}
```

Provisioning takes 1-3 minutes. The VPS runs cloud-init which installs all dependencies, sets up nginx, starts the agent, and starts the API.

### Get Instance

```
GET /api/projects/{project_id}/instances/{instance_id}
```

### Delete Instance

```
DELETE /api/projects/{project_id}/instances/{instance_id}
```

Destroys the VPS on Vultr and removes DNS records.

---

## Workspaces

### List Workspaces

```
GET /api/projects/{project_id}/workspaces
```

### Create Workspace

```
POST /api/projects/{project_id}/workspaces
```

```json
{
  "name": "backend",
  "type": "python",
  "description": "Main API"
}
```

Or clone from git:
```json
{
  "name": "backend",
  "type": "git",
  "repo": "https://github.com/user/repo.git",
  "branch": "main"
}
```

### Deploy Workspace (legacy SSH)

```
POST /api/projects/{project_id}/workspaces/{name}/deploy
```

> **Note**: This is the old SSH-based deploy. Use the .zar system instead (see below).

---

## Domains

### List Domains

```
GET /api/projects/{project_id}/domains
```

### Create Domain

```
POST /api/projects/{project_id}/domains
```

```json
{
  "domain": "app.mysite.com",
  "instance_id": "inst_m3n4o5"
}
```

Creates an A record on Cloudflare pointing to the instance IP.

---

## .zar System

All .zar endpoints are under `/api/projects/{project_id}/zar/`.

### Pack Workspace

```
POST /api/projects/{project_id}/zar/{workspace_name}/pack
```

```json
{
  "version": "1.2.0",
  "branch": "main"
}
```

Both fields optional. Version defaults to timestamp, branch defaults to "main".

Response:
```json
{
  "name": "backend",
  "version": "20260226.143012",
  "branch": "main",
  "hash": "sha256:a4f...",
  "size": 47128
}
```

### Push to R2

```
POST /api/projects/{project_id}/zar/{workspace_name}/push
```

```json
{
  "version": "1.2.0",
  "branch": "main"
}
```

Packs and uploads to Cloudflare R2. Response includes `r2_key`.

### Deploy to Instance

```
POST /api/projects/{project_id}/zar/{workspace_name}/deploy
```

```json
{
  "instance_id": "inst_m3n4o5",
  "version": "1.2.0",
  "branch": "main",
  "target_dir": "/opt/app",
  "restart_service": "setupo-app"
}
```

Tells the agent on the instance to:
1. Snapshot the current state
2. Download .zar from R2
3. Extract to target_dir
4. Install dependencies
5. Restart the service
6. Verify health — if fails, auto-rollback

### Ship (All-in-one)

```
POST /api/projects/{project_id}/zar/{workspace_name}/ship
```

```json
{
  "instance_id": "inst_m3n4o5",
  "branch": "main"
}
```

Does pack + push + deploy in one call. This is the recommended way to deploy.

### Rollback

```
POST /api/projects/{project_id}/zar/{workspace_name}/rollback
```

```json
{
  "instance_id": "inst_m3n4o5",
  "snapshot": "backend_20260225_100000.tar.gz"
}
```

`snapshot` is optional — defaults to the most recent one.

### Create Branch

```
POST /api/projects/{project_id}/zar/{workspace_name}/branch
```

```json
{
  "to": "staging",
  "from": "main"
}
```

Copies latest .zar from source branch to new branch in R2.

### Merge Branches

```
POST /api/projects/{project_id}/zar/{workspace_name}/merge
```

```json
{
  "from": "staging",
  "to": "main"
}
```

Copies latest from source to target branch.

### List Versions

```
GET /api/projects/{project_id}/zar/{workspace_name}/versions
```

Response:
```json
{
  "branches": {
    "main": "v20260226.143012",
    "staging": "v20260226.150000"
  },
  "versions": [
    "v20260224.100000.zar",
    "v20260225.120000.zar",
    "v20260226.143012.zar"
  ]
}
```

### Self-Update

```
POST /api/projects/{project_id}/zar/self-update
```

```json
{
  "instance_id": "inst_m3n4o5",
  "target": "agent"
}
```

`target` options: `agent`, `frontend`, `core`.

Updates the component on the instance without recreating the VPS.

---

## Agent Endpoints (port 8081)

These run on each VPS instance. Not called directly by users — the central API calls them. Documented here for debugging.

### Agent Login

```
POST http://{instance-ip}:8081/auth/login
```

### File Operations

```
GET    /files/list?path=/opt/app
GET    /files/read?path=/opt/app/config.toml
POST   /files/write   { "path": "...", "content": "..." }
DELETE /files/delete?path=/opt/app/old-file
```

### Command Execution

```
POST /exec/
{ "command": "systemctl status myapp" }
```

Response:
```json
{
  "stdout": "...",
  "stderr": "...",
  "returncode": 0
}
```

### Deploy (Agent-side)

```
POST   /deploy/pull          # Download .zar from R2 and deploy
POST   /deploy/upload        # Receive .zar via multipart upload
POST   /deploy/rollback      # Restore snapshot
GET    /deploy/current       # Current deploy state
GET    /deploy/snapshots     # List available snapshots
POST   /deploy/self-update   # Update agent/frontend/core
```

---

## Error Format

All errors return:
```json
{
  "error": "Human-readable error message"
}
```

HTTP status codes:
- `400` — Bad request / validation error
- `401` — Unauthorized (no token or expired)
- `403` — Forbidden (wrong scope)
- `404` — Resource not found
- `409` — Conflict (duplicate name, etc.)
- `422` — Validation error
- `502` — Provider error (Vultr/Cloudflare API failed)
- `503` — Service unavailable (agent unreachable)
