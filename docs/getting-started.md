# Getting Started with NSO

## What is NSO?

NSO is an infrastructure platform that lets you provision VPS instances, deploy code, and manage everything via API or CLI. No SSH between you and your servers — an agent on each VPS handles everything over HTTP.

Once your VPS is running, you can use it to SSH into **external** systems if needed.

## Quick Start (5 minutes)

### 1. Install

```bash
git clone https://github.com/lailaelghazouanitecnologia-cloud/setupo.git
cd setupo
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your Vultr API key
```

### 2. Start the server

```bash
python -m server.main
# → Running on http://localhost:8000
```

### 3. Login with the CLI

```bash
./nso config host http://localhost:8000
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

## Next Steps

- [CLI Reference](cli.md)
- [Failure Recovery](failure-recovery.md) — What can go wrong and how to fix it
- [API Reference](api-reference.md)
- [SKILL.md](../SKILL.md) — AI agent skill documentation
