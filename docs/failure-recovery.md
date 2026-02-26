# NSO — Failure Scenarios & Recovery

Everything that can go wrong, and how NSO handles it.

---

## 1. Deploy Failures

### 1.1 .zar extraction fails mid-deploy

**What happens**: The agent started extracting files but something broke (disk full, corrupted archive, permission error).

**Protection**: The agent takes a full snapshot BEFORE touching any files. If extraction fails at any point, the snapshot is restored automatically.

**Recovery**: Automatic. The service continues running the previous version.

```
nso ship backend inst_xxx
# ERROR Ship failed — auto-rollback executed
#   Reason: extraction error: disk full
#   Restored: backend_20260226_143012.tar.gz

# The service is still running the old version
# Fix the disk space issue, then retry
nso exec inst_xxx df -h
nso exec inst_xxx rm -rf /tmp/old-logs/*
nso ship backend inst_xxx
```

### 1.2 Service fails to start after deploy

**What happens**: New code was extracted, deps installed, but `systemctl restart` fails or the health check returns error.

**Protection**: After restart, the agent waits and checks if the service is responding. If not → auto-rollback.

**Recovery**: Automatic.

```
nso ship backend inst_xxx
# ERROR Ship failed — auto-rollback executed
#   Reason: health check failed after restart

# Check what went wrong
nso exec inst_xxx journalctl -u setupo-app -n 50
# Fix the bug in your code, then ship again
```

### 1.3 pip install / npm install fails

**What happens**: Dependencies can't be installed (network issue, incompatible package, missing system lib).

**Protection**: This happens AFTER snapshot but BEFORE restart. The old service is still running. If the install fails, extraction is rolled back.

**Recovery**: Automatic rollback. Fix dependencies and retry.

```
# Check what failed
nso exec inst_xxx cat /var/log/setupo-deploy.log

# Maybe a system package is needed
nso exec inst_xxx apt-get install -y libpq-dev
nso ship backend inst_xxx
```

### 1.4 Concurrent deploys (race condition)

**What happens**: Two `nso ship` commands run at the same time on the same instance.

**Protection**: The agent uses a deploy lock. Second deploy gets rejected with "deploy already in progress".

**Recovery**: Wait for the first deploy to finish, then run the second.

```
nso ship backend inst_xxx
# ERROR Deploy already in progress

# Wait and retry
sleep 30
nso ship backend inst_xxx
```

---

## 2. R2 Storage Failures

### 2.1 Upload to R2 fails

**What happens**: Network error or R2 service unavailable during `push`.

**Protection**: Push is atomic — if upload fails, nothing is written to R2. The previous latest.zar remains untouched.

**Recovery**: Retry.

```
nso push backend
# ERROR Push failed: connection timeout

# Retry
nso push backend
```

### 2.2 Download from R2 fails during deploy

**What happens**: The agent can't download the .zar from R2.

**Protection**: This happens BEFORE extraction, so nothing is modified. Snapshot was taken but no files were changed.

**Recovery**: The snapshot is cleaned up. Retry.

```
nso ship backend inst_xxx
# ERROR Deploy failed: R2 download timeout

# Check network from the instance
nso exec inst_xxx curl -I https://your-r2-endpoint.com
nso ship backend inst_xxx
```

### 2.3 Corrupted .zar file

**What happens**: The .zar in R2 is corrupted (truncated upload, bit flip).

**Protection**: The manifest contains a SHA-256 hash. The agent verifies the hash after download. Mismatch → abort before extraction.

**Recovery**: Re-pack and re-push.

```
nso ship backend inst_xxx
# ERROR Hash mismatch — .zar corrupted

nso pack backend
nso push backend
nso deploy backend inst_xxx
```

---

## 3. Self-Update Failures

### 3.1 Agent update kills the agent

**What happens**: During `nso update inst_xxx --target agent`, new code is extracted and `systemctl restart setupo-agent` runs. The agent process dies.

**Protection**: systemd has `Restart=always` with `RestartSec=3`. The new agent code starts automatically. If the new agent can't start (import error, syntax error), systemd keeps restarting it.

**Recovery**:

```
# If the agent comes back (new code works):
#   Everything is fine.

# If the agent doesn't come back (new code is broken):
# Option A: SSH into the VPS manually
ssh root@149.28.xx.xx
cd /opt/setupo/snapshots
# Restore the latest agent snapshot manually
tar xzf mms-metrics_*.tar.gz -C /opt/setupo/mms-metrics/
systemctl restart setupo-agent

# Option B: Create a new instance and migrate
nso inst create prod-2 --domain app.mysite.com
nso ship backend inst_new
```

### 3.2 Frontend update fails

**What happens**: `npm install` or `npm run build` fails during frontend self-update.

**Protection**: Snapshot taken before. If build fails, the old static files are still being served by nginx.

**Recovery**: Automatic rollback of the dashboard directory. Fix the frontend code and retry.

### 3.3 Core update kills the API

**What happens**: Core/server code updated, `systemctl restart setupo` runs, new code has errors.

**Protection**: Snapshot taken. Systemd will restart. If the API can't start, the agent is still running independently.

**Recovery**: Use the agent directly (it's on port 8081 and independent):

```
# Agent is still alive — rollback via direct agent call
curl -X POST http://149.28.xx.xx:8081/deploy/rollback \
  -H "Authorization: Bearer <agent-token>" \
  -H "Content-Type: application/json" \
  -d '{"target_dir": "/opt/setupo/server"}'
```

---

## 4. Instance / VPS Failures

### 4.1 VPS is unreachable

**What happens**: Network issue, VPS crashed, provider outage.

**Protection**: All .zar packages are in R2 (independent of any VPS). All snapshots are on the VPS disk.

**Recovery**:

```
# Check status
nso inst status inst_xxx

# If the VPS is dead, create a new one
nso inst create prod-2 --domain app.mysite.com
# Wait for provisioning...
nso ship backend inst_prod2
```

### 4.2 Cloud-init fails during provisioning

**What happens**: New VPS created but cloud-init script fails (package not available, git clone fails, etc.)

**Protection**: The agent reports progress during cloud-init. If it stops reporting, you know something failed.

**Recovery**:

```
# Check what happened
nso exec inst_xxx cat /var/log/cloud-init-output.log

# Or destroy and recreate
nso inst rm inst_xxx --force
nso inst create prod-1 --domain app.mysite.com
```

### 4.3 Disk full on VPS

**What happens**: Snapshots, logs, or app data fill the disk.

**Protection**: Max 5 snapshots per target (auto-rotation). But logs and app data can still fill the disk.

**Recovery**:

```
nso exec inst_xxx df -h
nso exec inst_xxx du -sh /opt/setupo/snapshots/*
nso exec inst_xxx journalctl --vacuum-size=100M
nso exec inst_xxx rm -rf /tmp/*
```

---

## 5. Auth / Security Failures

### 5.1 API key leaked

**Recovery**: Delete the project and create a new one with a new key. Or rotate the key via admin.

```
nso projects rm proj_leaked --force
nso projects create my-saas
# New API key generated
```

### 5.2 Agent password wrong

```
nso exec inst_xxx ls
# ERROR Agent login failed

# Set the correct password
export AGENT_ADMIN_PASSWORD=correct_password
nso exec inst_xxx ls
```

### 5.3 JWT token expired

```
nso projects ls
# ERROR Unauthorized — run: nso login

nso login -e admin@example.com
```

---

## 6. Network / Timeout Issues

### 6.1 Slow deploy (timeout)

**What happens**: Large workspace, slow R2 download, or slow pip install causes the HTTP request to timeout.

**Protection**: The deploy continues on the agent even if the HTTP connection drops. The agent is autonomous.

**Recovery**:

```
nso ship backend inst_xxx
# ERROR Connection timeout

# The deploy might still be running on the agent
# Wait a minute and check
nso exec inst_xxx systemctl status setupo-app
```

### 6.2 R2 region latency

**What happens**: VPS is in one region, R2 in another. Download is slow.

**Mitigation**: Use R2 public URL if configured. Consider placing R2 and VPS in the same region.

---

## 7. Data Loss Prevention

### 7.1 .env file preserved

The .zar packer EXCLUDES `.env` from archives. During extraction, existing `.env` files are NEVER overwritten. Environment configuration survives all deploys and rollbacks.

### 7.2 Snapshot retention

- Max 5 snapshots per target per instance
- Oldest rotated out when limit reached
- Each snapshot is a complete tar.gz of the previous state

### 7.3 R2 versioning

- Every push creates a new versioned .zar (never overwrites)
- `latest.zar` is updated to point to the newest version
- All previous versions remain downloadable
- Branches are independent copies

---

## 8. Recovery Cheat Sheet

| Problem | Command |
|---------|---------|
| Bad deploy | `nso rollback backend inst_xxx` |
| Service down | `nso exec inst_xxx systemctl restart setupo-app` |
| Check logs | `nso exec inst_xxx journalctl -u setupo-app -n 100` |
| Disk full | `nso exec inst_xxx df -h` |
| Agent dead | SSH manually, restore from snapshot |
| API dead | Use agent directly on :8081 |
| VPS dead | `nso inst create new-prod`, then `nso ship` |
| R2 upload failed | `nso push backend` (retry) |
| Corrupted .zar | `nso pack backend && nso push backend` |
| Auth expired | `nso login` |
| Everything broken | Create new instance, ship latest from R2 |

---

## 9. Prevention Best Practices

1. **Always test on staging first**
   ```
   nso branch backend staging
   nso ship backend inst_staging -b staging
   # verify
   nso merge backend staging main
   nso ship backend inst_prod
   ```

2. **Check before shipping**
   ```
   nso versions backend
   nso exec inst_xxx df -h
   ```

3. **Keep snapshots healthy**
   ```
   nso exec inst_xxx ls -la /opt/setupo/snapshots/
   ```

4. **Monitor after deploy**
   ```
   nso exec inst_xxx curl -s http://localhost:3000/health
   nso exec inst_xxx journalctl -u setupo-app -f
   ```

5. **Use branches for risky changes**
   ```
   nso branch backend experiment
   nso ship backend inst_test -b experiment
   # if good: nso merge backend experiment main
   # if bad: nothing happened to main
   ```
