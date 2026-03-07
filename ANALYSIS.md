# Roternos — Audit Report

> Full security, quality, and architecture analysis of the NSO platform.
> Date: 2026-03-07

---

## Executive Summary

Roternos (repo `setupo`) is a full IaaS platform (~52K LOC) with a modular FastAPI backend, per-VPS agent, Next.js dashboard, and a custom `.zar` deploy system. The codebase is ambitious and well-structured, but has **5 critical**, **12 high**, and **20+ medium** severity issues that need attention before production hardening.

---

## 1. CRITICAL Vulnerabilities

### 1.1 Shell Injection in Agent Command Execution
- **Files**: `vm/agent/exec.py`, `vm/agent/deploy.py`, `vm/agent/supervisor.py`
- **Issue**: Uses `subprocess_shell` throughout. Blacklist in `exec.py` uses substring matching, easily bypassed (`"rm -rf /"` blocked but `"rm -rf / "` is not). Environment variables in deploy use incomplete escaping (`$(whoami)` executes inside single quotes). Supervisor runs `deploy.toml` commands without validation.
- **Impact**: Remote Code Execution (RCE)
- **Fix**: Replace all `create_subprocess_shell` with `create_subprocess_exec` using arrays. Switch from blacklist to whitelist in exec.py. Base64-encode env vars before injection.

### 1.2 Financial Race Conditions in Billing
- **Files**: `nso/engine/billing/routes.py:715-762`, `nso/engine/billing/service.py:1330-1401`
- **Issue**: Top-up and charge operations read balance, compute new value, then write — not atomic. Two concurrent requests read the same balance and cause overdraft. Invoice finalization does multiple `db.update()` calls without a transaction wrapper.
- **Impact**: Financial loss, inconsistent billing state
- **Fix**: Use atomic SQL: `UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?`. Wrap multi-table operations in `BEGIN EXCLUSIVE` transactions.

### 1.3 Blockchain Ledger Lock Not Distributed
- **File**: `nso/engine/admin/ledger.py:175-194`
- **Issue**: Per-user chain lock is a Python `dict` in memory. With multiple uvicorn workers, each process has its own lock dict — chain corruption is possible.
- **Impact**: Audit trail integrity compromised
- **Fix**: Use SQLite `BEGIN EXCLUSIVE TRANSACTION` or database-level advisory locks.

### 1.4 No Database Transaction Support
- **File**: `nso/shared/db.py:123-193`
- **Issue**: `insert()`, `update()`, `delete()` each commit immediately. No multi-statement transaction support exists in the CRUD layer.
- **Impact**: Race conditions and data inconsistency across all modules that do multi-step operations
- **Fix**: Add a `db.transaction()` async context manager.

### 1.5 JWT Secret Auto-Generated on Restart
- **File**: `nso/shared/auth/jwt.py:9`
- **Issue**: If `NSO_JWT_SECRET` is not set, a random secret is generated at import time. Server restart invalidates all tokens.
- **Impact**: All users logged out on every restart/deploy
- **Fix**: Require `NSO_JWT_SECRET` in production; fail startup if absent.

---

## 2. HIGH Severity Issues

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| 2.1 | `deploy/service.py` ExecStart | User-provided command injected into systemd unit unescaped | Validate against strict regex |
| 2.2 | `auth/service.py:191-216` | Subdomain claim race condition (check-then-act) | Use UNIQUE constraint + INSERT OR IGNORE |
| 2.3 | `storage/service.py:196-204` | Read-modify-write race on `branches.json` in R2 | Use conditional put / ETag |
| 2.4 | `billing/service.py:786` | Coupon discount has no maximum cap | Add `min(discount, subtotal_cents)` |
| 2.5 | `deploy/service.py:92-95` | State set to DEPLOYING before operations; stays stuck on failure | try/finally with ERROR state in except |
| 2.6 | `vm/agent/deploy.py:65` | `env = {**os.environ, **req.env}` allows override of PATH, LD_PRELOAD | Filter system-critical env keys |
| 2.7 | `nso/shared/db.py` | Single global SQLite connection, no pooling | Add connection health checks and reconnection |
| 2.8 | `nso/shared/ratelimit.py:31` | Rate limit buckets never purged — unbounded memory growth | Add TTL / LRU eviction for IP buckets |
| 2.9 | `nso/shared/db.py:53-81` | Migrations have no versioning, idempotency, or rollback | Track migrations in `schema_migrations` table |
| 2.10 | `vm/agent/exec.py` | BLOCKED_PATTERNS misses fork bombs, `/dev/sda` writes, resource exhaustion | Use command whitelist |
| 2.11 | `billing/routes.py:210-213` | No URL validation on `success_url`/`cancel_url` (open redirect) | Validate against allowed domains |
| 2.12 | `compute/service.py:145-159` | Failed provisioning leaves orphan VPS running at Vultr | Auto-cleanup on timeout + retry |

---

## 3. MEDIUM Severity Issues

### Security
- Admin password stored as plaintext in memory (`resolve.py:35-51`) — store only hash
- `ORDER BY` validation incomplete in `db.py:99-106` — could allow blind SQLite injection
- Tokens in localStorage vulnerable to XSS — migrate to httpOnly cookies
- No request deduplication / idempotency keys — duplicate POSTs cause duplicates
- Agent R2 credentials sent in request body (`deploy.py:56-60`) — fetch server-side

### Architecture
- No CI/CD pipeline (no `.github/workflows/`, no Dockerfile, no docker-compose)
- Dev/prod detection uses fragile path heuristic (`config.py:69-92`) — use explicit `NSO_ENV`
- Middleware order is undocumented and fragile (`main.py:136-149`)
- Admin hosts hardcoded (`main.py:24`) — should be configurable via env
- Circular import risk in route registration (`main.py:157-177`)
- `openai>=1.0.0` in requirements.txt has no upper bound — may break

### Frontend
- No API response validation (zod or similar)
- Panels are 36-49KB without memoization — split + React.memo
- Deploy panel messages grow unbounded — add virtualization
- No cross-tab session sync — listen to localStorage `storage` events
- Stream abort handling has race conditions in deploy-panel
- Event listener duplicated on every store import (`dashboard-store.ts:134-137`)

### Agent
- `/tmp` in ALLOWED_ROOTS lets users read other processes' temp files
- Symlink targets not validated — could escape ALLOWED_ROOTS
- No pagination on directory listing — huge directories crash response
- Supervisor health checks are sequential — should be parallel
- No process resource limits (CPU/memory) in supervisor
- No zombie process cleanup on failed waits

---

## 4. Test Coverage Gaps

| Module | Has Tests | Priority |
|--------|-----------|----------|
| auth | Yes | - |
| billing | Yes | - |
| blockchain | Yes | - |
| email | Yes | - |
| orchestrator | Yes | - |
| **compute** | **No** | **P0** — VPS provisioning |
| **deploy** | **No** | **P0** — deploy pipeline |
| **storage/R2** | **No** | **P0** — .zar operations |
| **agent (exec/files)** | **No** | **P0** — command execution |
| **projects** | **No** | P1 |
| **addons** | **No** | P1 |
| **dns** | **No** | P2 |
| **notifications** | **No** | P2 |
| **frontend** | **No** | P1 — needs Playwright/Cypress |

Current coverage: ~30% of modules. The most dangerous code (exec, deploy, compute) has zero tests.

---

## 5. Missing Infrastructure

| Item | Status | Recommendation |
|------|--------|----------------|
| CI/CD | None | GitHub Actions: lint (ruff) + test (pytest) + build (next) |
| Containerization | None | Dockerfile for local dev; keep cloud-init for prod |
| Structured logging | Print/basic | structlog with correlation IDs |
| Error tracking | None | Sentry integration |
| DB backups | None | Cron SQLite `.backup` → R2 |
| Monitoring | Basic health | Prometheus metrics (latency, errors, deploys) |
| Secrets management | .env file | At minimum, encrypted at rest |
| API documentation | None | Auto-generate OpenAPI docs from FastAPI |
| Load testing | None | Locust or k6 for billing/deploy paths |

---

## 6. Improvement Roadmap

### Phase 1 — Security Hardening (Week 1-2)
1. Replace `subprocess_shell` → `subprocess_exec` in all agent code
2. Add `db.transaction()` context manager + atomic billing operations
3. Filter system env vars in agent deploy
4. Switch exec.py to command whitelist
5. Fix ledger lock with exclusive SQLite transactions
6. Require JWT_SECRET in production
7. Validate redirect URLs in billing checkout

### Phase 2 — Stability (Week 3-4)
8. Add tests for compute, deploy, storage, agent exec/files
9. Set up GitHub Actions CI (lint + test + build)
10. Pin all dependency versions
11. Add migration versioning/tracking
12. Fix rate limit memory leak (TTL + LRU)
13. Add connection health checks to db.py

### Phase 3 — Operations (Week 5-6)
14. Structured logging with correlation IDs
15. Automated SQLite backups to R2
16. Monitoring (Prometheus/Grafana)
17. Deploy log rotation/TTL
18. Sentry error tracking
19. Add `NSO_ENV` explicit dev/prod config

### Phase 4 — Frontend & DX (Week 7-8)
20. Migrate auth tokens to httpOnly cookies
21. Add zod validation for API responses
22. Split large panel components + React.memo
23. E2E tests with Playwright
24. Cross-tab session sync
25. OpenAPI docs generation

---

## 7. Architecture Strengths

Despite the issues above, the codebase has several strong design choices:

- **Modular engine**: Auto-discovery via `config.toml` per module is clean and extensible
- **Zero-dependency R2**: Custom HMAC S3v4 signing avoids heavy AWS SDK dependency
- **.zar deploy**: Simple tar.gz + manifest is lightweight and fast vs Docker
- **Dual auth pattern**: Separate tokens for central API vs agent is architecturally sound
- **Blockchain ledger**: Hash-linked audit trail for billing is sophisticated
- **Supervisor reconciliation**: Desired vs actual state loop is a good Kubernetes-inspired pattern
- **Deploy agent**: LLM-powered conversational deploy is innovative

The platform is well-conceived. The improvements above will harden it for production use.
