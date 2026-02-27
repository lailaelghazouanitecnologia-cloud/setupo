# NSO CLI Reference

## Installation

```bash
# From the repo root
./nso <command>

# Or add to PATH
ln -s /opt/setupo/nso /usr/local/bin/nso
```

## Global Options

```
--json        JSON output (for scripting)
-p, --project Project ID (or set NSO_PROJECT)
```

## Commands

### Authentication

```bash
nso login -e admin@example.com           # Email/password
nso login -k sk_live_abc123              # API key
nso login --host https://nso.dev    # Set host + login
nso logout                               # Clear token
nso config                               # Show config
nso config host https://nso.dev     # Set host
```

### Deploy Operations

```bash
# All-in-one: pack + push + deploy
nso ship <workspace> <instance>
nso ship backend inst_xxx
nso ship backend inst_xxx -v 2.0.0 -b staging

# Deploy from R2 (already pushed)
nso deploy <workspace> <instance>
nso deploy backend inst_xxx --target-dir /opt/myapp

# Rollback to previous snapshot
nso rollback <workspace> <instance>
nso rollback backend inst_xxx -s backend_20260225.tar.gz

# Just pack (no upload)
nso pack <workspace>
nso pack backend -v 1.0.0

# Just push to R2 (no deploy)
nso push <workspace>
nso push backend -b staging

# Self-update component on instance
nso update <instance> --target agent|frontend|core
nso update inst_xxx --target agent
```

### Versioning

```bash
# List versions and branches
nso versions <workspace>

# Create branch from main
nso branch <workspace> <name>
nso branch backend staging
nso branch backend hotfix --from staging

# Merge
nso merge <workspace> <from> <to>
nso merge backend staging main
```

### Resources

```bash
# Projects
nso projects ls
nso projects create my-saas
nso projects rm proj_xxx -f

# Instances
nso inst ls
nso inst create prod-1 --domain app.com --plan vc2-1c-2gb -r ewr
nso inst status inst_xxx
nso inst rm inst_xxx -f

# Workspaces
nso ws ls
nso ws create backend --type python
nso ws create my-app --repo https://github.com/user/repo.git
```

### Execute Commands

```bash
# Run on instance (via agent HTTP)
nso exec <instance> <command...>
nso exec inst_xxx ls -la /opt/app
nso exec inst_xxx systemctl status myapp
nso exec inst_xxx journalctl -u myapp -n 50

# SSH to external systems FROM the instance
nso exec inst_xxx ssh user@external-server uptime
nso exec inst_xxx curl https://api.external.com/health

# Longer timeout
nso exec inst_xxx --timeout 120 npm run build
```

### Diagnostics

```bash
nso status    # Quick overview
nso doctor    # Full diagnostic
```

## Scripting

### CI/CD Pipeline

```bash
#!/bin/bash
set -euo pipefail
export NSO_HOST=https://nso.dev
export NSO_TOKEN=sk_live_abc123
export NSO_PROJECT=proj_xxx

nso ship backend inst_staging -b staging
nso exec inst_staging python -m pytest /opt/app/tests/
nso ship backend inst_prod
```

### Batch Update

```bash
for inst in inst_prod1 inst_prod2 inst_prod3; do
    echo "Shipping to $inst..."
    nso ship backend "$inst" || echo "FAILED: $inst"
done
```

### Blue-Green Deploy

```bash
GREEN=inst_green
nso ship backend $GREEN
HEALTH=$(nso exec $GREEN curl -s localhost:3000/health)
if echo "$HEALTH" | grep -q '"ok"'; then
    echo "Green healthy — switch DNS"
else
    nso rollback backend $GREEN
    exit 1
fi
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error |
| Other | Exit code from `exec` |
