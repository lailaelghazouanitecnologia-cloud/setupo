# NSO — Análisis Estructural Completo del Proyecto

## Resumen

| Área | Archivos | Líneas | Bytes |
|------|----------|--------|-------|
| `nso/` (central server) | ~100 .py | 28,922 | — |
| `vm/` (agent + CLI) | ~15 .py | 5,640 | — |
| `client/` (dashboards) | ~30 .ts/.tsx | 13,930 | — |
| `tests/` | 7 .py | 1,163 | — |
| **Total** | **~152** | **49,655** | — |

---

## 1. Backend — `nso/engine/` (13 módulos, 28,922 líneas)

### Tamaño por módulo

| Módulo | Archivos | Líneas | Patrón estándar? |
|--------|----------|--------|-----------------|
| `addons` | 13 | 4,476 | Parcial (muchos sub-routes) |
| `compute` | 19 | 3,933 | No (pool, quota, hosts, vms mezclados) |
| `orchestrator` | 18 | 3,657 | Parcial (reconciler muy grande) |
| `billing` | 4 | 2,871 | No (service.py monolítico) |
| `admin` | 5 | 2,095 | No (analytics.py monolítico) |
| `deploy_agent` | 5 | 1,497 | Sí |
| `validator` | 5 | 1,216 | Sí |
| `workspace` | 9 | 1,286 | Sí |
| `storage` | 6 | 1,074 | Sí |
| `build` | 4 | 667 | Sí |
| `deploy` | 6 | 683 | Sí |
| `auth` | 5 | 540 | Sí |
| `notifications` | 4 | 432 | Sí |
| `dns` | 4 | 255 | Sí |
| `projects` | 4 | 236 | Sí |

### Archivos monolíticos (> 600 líneas) — DEBEN PARTIRSE

| Archivo | Líneas | Problema | Propuesta |
|---------|--------|----------|-----------|
| `billing/service.py` | **1,798** | Una clase con 40+ métodos: plans, subs, invoices, wallets, coupons, credit notes, metrics, usage, payments, taxes, events | Partir en: `plan_service.py`, `subscription_service.py`, `invoice_service.py`, `wallet_service.py`, `coupon_service.py`, `usage_service.py`, `payment_service.py` |
| `admin/analytics.py` | **931** | Funciones monolíticas de analytics, cashflow, snapshots | Partir en: `revenue.py`, `growth.py`, `cashflow.py`, `snapshots.py` |
| `billing/routes.py` | **833** | Router monolítico con 40+ endpoints | Partir en sub-routers por área |
| `admin/routes.py` | **696** | Admin routes mezcladas | Partir en: `admin_user_routes.py`, `admin_analytics_routes.py`, `admin_infra_routes.py` |
| `compute/pool.py` | **644** | Pool state + CRUD + logic mezclados | Separar state/CRUD/operations |
| `orchestrator/reconciler.py` | **599** | Reconciliación masiva | OK por complejidad intrínseca |
| `addons/ai_apps_service.py` | **561** | AI apps session + pipeline + tools | Partir en: `ai_session.py`, `ai_pipeline.py`, `ai_tools.py` |

### Patrón estándar de módulos

Cada módulo debería tener:
```
engine/{module}/
├── config.toml      # Metadata del módulo
├── routes.py        # FastAPI routes (thin layer)
├── service.py       # Business logic
├── migrations.py    # Schema SQL
└── models.py        # Pydantic models (opcional)
```

**Módulos que no siguen el patrón:**
- `compute/` — 19 archivos, incluye pool, quota, hosts, vm_manager, ready, health, pool_reconciler. Debería dividirse en 2-3 submódulos: `compute/instances/`, `compute/pool/`, `compute/hosts/`
- `addons/` — 13 archivos mezclando plugins, modules, connectors, marketplace, AI apps. El AI apps debería ser su propio módulo `engine/ai/`
- `orchestrator/` — 18 archivos con monitor, reconciler, scheduler, loadbalancer, LB proxy, LB health, states. Correcto dado la complejidad

---

## 2. Shared — `nso/shared/` (7 archivos, ~1,100 líneas)

| Archivo | Líneas | Estado |
|---------|--------|--------|
| `manager.py` | 308 | Bien — ServiceManager con health checks |
| `models.py` | 293 | Bien — Pydantic models compartidos |
| `events.py` | 235 | Bien — Event bus pub/sub |
| `db.py` | 193 | Bien — CRUD genérico con validación SQL |
| `auth/resolve.py` | 152 | Bien — Token resolution 3-way |
| `ratelimit.py` | 86 | Bien |
| `auth/jwt.py` | 81 | Bien |
| `deps.py` | 41 | Bien |
| `errors.py` | 30 | Bien |
| `auth/keys.py` | 18 | Bien |

**Observaciones:**
- `db.py` usa f-strings para SQL pero con `_validate_identifier()` — protegido contra injection
- `events.py` es fire-and-forget sin guaranteed delivery — OK para nuestro caso
- `manager.py` tiene service dependencies con restart automático — buena infra

---

## 3. VM Agent — `vm/agent/` (13 archivos, 4,487 líneas)

| Archivo | Líneas | Función |
|---------|--------|---------|
| `pipeline.py` | 773 | Pipeline de deploy con fases |
| `supervisor.py` | 759 | Process supervisor para deploys |
| `pool_handler.py` | 700 | Handler para pool VMs |
| `deploy.py` | 636 | Deploy .zar, snapshot, rollback |
| `ai.py` | 325 | AI agent chat (deploy assistant) |
| `envvars.py` | 262 | Env var CRUD con buckets |
| `main.py` | 232 | Entry point + router mount |
| `store.py` | 228 | SQLite metrics store |
| `files.py` | 220 | File operations (browse/read/write) |
| `exec.py` | 144 | Command execution |
| `auth.py` | 125 | Agent-local JWT auth |
| `models.py` | 83 | Agent models |

**Problemas:**
- `pipeline.py` (773 líneas) + `supervisor.py` (759 líneas) + `pool_handler.py` (700 líneas) son archivos grandes pero con responsabilidades distintas — aceptable
- `deploy.py` (636 líneas) mezcla deploy, snapshot, rollback, self-update — podría partirse

---

## 4. VM CLI — `vm/cli/` (3 archivos, 1,153 líneas)

| Archivo | Líneas | Función |
|---------|--------|---------|
| `main.py` | 897 | Todos los comandos CLI |
| `client.py` | 157 | HTTP client con auth/retries |
| `output.py` | 98 | Terminal formatting helpers |

**Problema:** `main.py` con 897 líneas tiene TODOS los comandos (login, ship, exec, instances, projects, workspaces, deploy, secrets, etc.). Debería partirse en subcommands.

---

## 5. Tests — `tests/` (7 archivos, 1,163 líneas)

| Archivo | Líneas | Qué testea |
|---------|--------|------------|
| `conftest.py` | — | Fixtures |
| `test_auth.py` | — | Auth endpoints |
| `test_billing.py` | — | Billing service |
| `test_blockchain.py` | — | Blockchain ledger |
| `test_email.py` | — | Email service |
| `test_orchestrator.py` | — | Orchestrator |

**Cobertura MÍNIMA — áreas SIN tests:**
- `compute/` (pool, VMs, hosts, quota) — 0 tests
- `deploy/` (deploy pipeline, storage, .zar) — 0 tests
- `workspace/` (CRUD, config, secrets) — 0 tests
- `addons/` (plugins, connectors, marketplace, AI) — 0 tests
- `admin/` (analytics, user management) — 0 tests
- `dns/` (domains) — 0 tests
- `projects/` (CRUD) — 0 tests
- VM agent (deploy, files, exec) — 0 tests
- CLI — 0 tests
- Frontend — 0 tests

**Solo 5 de 15 módulos tienen tests. Cobertura estimada: ~15%.**

---

## 6. `main.py` — Registro de Rutas

`nso/main.py` (244 líneas) tiene:
- `ROUTE_REGISTRY` dict (no usado — vestigio del auto-discovery)
- 25+ `app.include_router()` calls
- `lifespan` con imports inline condicionados a `SERVER_MODE`
- 3 middlewares custom (AdminHost, ServerMode, RateLimit + LBProxy)

**Problema:** `ROUTE_REGISTRY` (líneas 63-73) define prefijos pero NO se usa para auto-discovery. Las rutas se registran manualmente debajo. Es código muerto.

---

## 7. `config.py` — Configuración

Bien estructurada. Usa `os.environ.get()` con defaults. Helpers para `db_path()`, `project_dir()`, `workspace_path()`, `r2_config()`.

**Problema menor:** `workspace_dir(project_id, name)` ignora `project_id` — solo usa `name`. El parámetro es misleading.

---

## 8. Problemas Transversales

### 8.1 Archivos Muertos/Obsoletos
- `ROUTE_REGISTRY` en main.py — no usado
- `ADMIN_MODULES` en main.py — no usado
- `workspace_dir()` parameter `project_id` — ignorado

### 8.2 Inconsistencias en Error Handling
- Backend usa `NsoError` hierarchy (30 líneas) — limpio
- Algunos módulos usan `raise HTTPException()` directamente en service.py en vez de `NsoError`
- Agent usa excepciones nativas sin hierarchy

### 8.3 Logging
- Backend usa `logging.getLogger("nso.xxx")` — consistente
- Agent no sigue el mismo patrón — usa print() en algunos lugares

### 8.4 Validación
- `db.py` valida SQL identifiers — bueno
- No hay validación de input en varios endpoints (confía en Pydantic)
- Agent exec.py no sanitiza comandos — intencional pero riesgoso

---

## 9. Plan de Acción Recomendado

### Prioridad ALTA (deuda técnica crítica)

1. **Partir `billing/service.py`** (1,798 líneas → 7 archivos)
2. **Partir `admin/analytics.py`** (931 líneas → 4 archivos)
3. **Mover AI apps a su propio módulo** `engine/ai/`
4. **Eliminar ROUTE_REGISTRY y ADMIN_MODULES** de main.py (código muerto)
5. **Crear tests** para compute, deploy, workspace, projects (cobertura 15% → 50%+)

### Prioridad MEDIA (modularidad)

6. Partir `compute/` en submódulos (instances, pool, hosts)
7. Partir `billing/routes.py` en sub-routers
8. Partir `vm/cli/main.py` en subcommands
9. Unificar error handling: NsoError en vez de HTTPException en services

### Prioridad BAJA (mejoras incrementales)

10. Logging consistente en agent (logger vs print)
11. Fix `workspace_dir()` parameter misleading
12. Documentar event naming conventions
