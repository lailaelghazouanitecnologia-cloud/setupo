# NSO — Análisis Estructural Completo del Proyecto

## Resumen

| Área | Archivos | Líneas |
|------|----------|--------|
| `nso/` (central server) | ~100 .py | 28,922 |
| `vm/` (agent + CLI) | ~15 .py | 5,640 |
| `client/` (dashboards) | ~30 .ts/.tsx | 13,930 |
| `tests/` | 7 .py | 1,163 |
| **Total** | **~152** | **49,655** |

---

## 1. Backend — `nso/engine/` (15 módulos)

### Tamaño por módulo

| Módulo | Archivos | Líneas | Patrón estándar? |
|--------|----------|--------|-----------------|
| `addons` | 13 | 4,476 | Parcial — AI apps debería ser módulo propio |
| `compute` | 19 | 3,933 | No — pool/quota/hosts/vms mezclados |
| `orchestrator` | 18 | 3,657 | Parcial — reconciler muy grande |
| `billing` | 4 | 2,871 | No — service.py monolítico |
| `admin` | 5 | 2,095 | No — analytics.py monolítico |
| `deploy_agent` | 5 | 1,497 | Sí |
| `workspace` | 9 | 1,286 | Parcial — mezcla files/git/sharing/platform |
| `validator` | 5 | 1,216 | Sí |
| `storage` | 6 | 1,074 | Parcial — .zar ops mezcladas con CRUD |
| `build` | 4 | 667 | Sí |
| `deploy` | 6 | 683 | Sí |
| `auth` | 5 | 540 | Sí |
| `notifications` | 4 | 432 | Sí |
| `dns` | 4 | 255 | Sí |
| `projects` | 4 | 236 | Sí |

### Archivos monolíticos que DEBEN partirse

| Archivo | Líneas | Responsabilidades mezcladas | Propuesta |
|---------|--------|----------------------------|-----------|
| `billing/service.py` | **1,798** | Plans, subs, invoices, wallets, coupons, credit notes, metrics, usage, payments, taxes, events (40+ métodos) | `plan_service.py`, `subscription_service.py`, `invoice_service.py`, `wallet_service.py`, `coupon_service.py`, `usage_service.py`, `payment_service.py` |
| `admin/analytics.py` | **931** | Revenue, growth, cashflow, snapshots en funciones monolíticas | `revenue.py`, `growth.py`, `cashflow.py`, `snapshots.py` |
| `billing/routes.py` | **833** | Router monolítico con 40+ endpoints | Sub-routers por área (plan_routes, sub_routes, invoice_routes, wallet_routes) |
| `admin/routes.py` | **696** | Admin user mgmt + analytics + infra routes mezcladas | `admin_user_routes.py`, `admin_analytics_routes.py`, `admin_infra_routes.py` |
| `compute/pool.py` | **644** | Pool state + CRUD + logic mezclados | Separar state/CRUD/operations |
| `orchestrator/reconciler.py` | **599** | OK por complejidad intrínseca |
| `addons/ai_apps_service.py` | **561** | AI session + pipeline + tools | Mover a `engine/ai/` como módulo propio |
| `storage/routes.py` | **588** | .zar pack/push/deploy/branch/merge mezclado con storage CRUD | Separar zar_routes.py |
| `workspace/routes.py` | **431** | File ops + git + sharing + platform workspaces | `routes_base.py`, `routes_sharing.py`, `routes_platform.py` |

---

## 2. Shared — `nso/shared/` (~1,400 líneas)

| Archivo | Líneas | Estado |
|---------|--------|--------|
| `manager.py` | 308 | Bien — ServiceManager con health checks y dependency ordering |
| `models.py` | 293 | Bien — Pydantic models compartidos |
| `events.py` | 235 | Bien — Event bus pub/sub, fire-and-forget |
| `db.py` | 193 | Bien — CRUD genérico con SQL injection protection |
| `auth/resolve.py` | 152 | Bien — Token resolution 3-way (admin/user/API key) |
| `ratelimit.py` | 86 | Bien — Sliding window per IP |
| `auth/jwt.py` | 81 | Bien — HS256 + PBKDF2 |
| `deps.py` | 41 | Bien — Clean dependency injection |
| `errors.py` | 30 | Bien — NsoError hierarchy |
| `auth/keys.py` | 18 | Bien — sk_live_ generation |

**Problemas encontrados:**
1. `db.py:18-22` — JSON/BOOL fields hardcodeados en `JSON_FIELDS`/`BOOL_FIELDS` frozensets. Añadir nuevo campo JSON requiere cambio en db.py
2. `events.py:219-220` — Silently ignores table creation failures con `pass`
3. `resolve.py:74-88` — `PUBLIC_PATHS` hardcodeado, difícil mantener al añadir endpoints públicos

---

## 3. `main.py` — Problemas Específicos

| Línea | Problema |
|-------|----------|
| 63-73 | `ROUTE_REGISTRY` — **CÓDIGO MUERTO**, las rutas se registran manualmente en líneas 187-212 |
| 75 | `ADMIN_MODULES` — **CÓDIGO MUERTO**, no se usa |
| 92-102 | ServiceManager imported inside conditional block — riesgo de import circular |
| 145-146 | `LBProxyMiddleware` imported condicionalmente — cambia behavior en load-time |
| 223-226 | `__import__("nso.engine.workspace.share_routes")` — magic string import |

---

## 4. VM Agent — `vm/agent/` (13 archivos, 4,487 líneas)

| Archivo | Líneas | Estado |
|---------|--------|--------|
| `pipeline.py` | 773 | Grande pero OK — pipeline de deploy con fases |
| `supervisor.py` | 759 | Grande pero OK — process supervisor |
| `pool_handler.py` | 700 | Grande pero OK — pool VM handler |
| `deploy.py` | 636 | Debería partirse — mezcla deploy/snapshot/rollback/self-update |
| `ai.py` | 325 | OK — AI deploy assistant |
| `envvars.py` | 262 | OK — Env var CRUD con buckets |
| `main.py` | 232 | OK — Entry point |
| `store.py` | 228 | OK — SQLite metrics |
| `files.py` | 220 | OK — File ops con ALLOWED_ROOTS sandboxing |
| `exec.py` | 144 | OK — Command execution |
| `auth.py` | 125 | **DUPLICA** nso/shared/auth/jwt.py |
| `models.py` | 83 | OK |

**Problemas críticos:**
1. **`auth.py` duplica lógica JWT** de `nso/shared/auth/jwt.py` — parches de seguridad en uno no se propagan al otro
2. **`auth.py:39`** — Default password hash "zarnlok4123" hardcodeado como placeholder
3. **`files.py:16`** — `ALLOWED_ROOTS` hardcodeado globalmente, no configurable per-project

---

## 5. VM CLI — `vm/cli/` (3 archivos, 1,153 líneas)

| Archivo | Líneas | Problema |
|---------|--------|---------|
| `main.py` | **897** | TODOS los comandos en un solo archivo — partir en subcommands |
| `client.py` | 157 | Usa urllib en vez de httpx — catch genérico pierde contexto |
| `output.py` | 98 | OK — Terminal formatting |

---

## 6. Tests — COBERTURA CRÍTICA

| Tests que existen | Tests que faltan |
|-------------------|-----------------|
| `test_auth.py` | `test_projects.py` |
| `test_billing.py` | `test_compute.py` |
| `test_blockchain.py` | `test_deploy.py` |
| `test_email.py` | `test_workspace.py` |
| `test_orchestrator.py` | `test_storage.py` |
| | `test_addons.py` |
| | `test_admin.py` |
| | `test_dns.py` |
| | Tests de integración end-to-end |
| | Tests del agent |
| | Tests del CLI |
| | Tests del frontend |

**Cobertura estimada: ~15%. Solo 5/15 módulos tienen tests.**

---

## 7. Dependencias Circulares Detectadas

| De | A | Línea | Tipo |
|----|---|-------|------|
| `auth/routes.py` | `notifications/service.py` | :9 | Import directo |
| `compute/routes.py` | `deploy/service.py` | :84 | Import inline (lazy) para esconder el ciclo |
| `admin/routes.py` | storage, compute, auth services | múltiples | Tight coupling |

**Solución:** Usar el event bus (`nso/shared/events.py`) en vez de imports directos entre módulos.

---

## 8. Seguridad

### Problemas encontrados

| Severidad | Ubicación | Problema |
|-----------|-----------|----------|
| ALTA | `config.py:46` | `ADMIN_PASSWORD` en env var plano — debería usar vault |
| ALTA | `agent/auth.py:39` | Default password hash visible en código |
| ALTA | `shared/auth/jwt.py:9` | JWT_SECRET auto-generado si no se configura — producción debería fallar |
| MEDIA | `agent/exec.py` | Ejecución de comandos sin sanitización (intencional pero riesgoso) |
| MEDIA | `agent/files.py:29` | Path validation con string prefix — mejor usar `pathlib.resolve().relative_to()` |
| MEDIA | `storage/routes.py:116` | R2 credentials pasadas en plain JSON |
| BAJA | `resolve.py:74-88` | PUBLIC_PATHS hardcodeado |

### Cosas bien hechas
- Token validation usa `hmac.compare_digest` (constant-time) ✓
- `db.py` usa parameterized queries ✓
- `db.py:94-96` valida SQL identifiers ✓
- Rate limiting en middleware ✓
- Admin host restriction ✓

---

## 9. Inconsistencias de Datos

| Problema | Ubicación |
|----------|-----------|
| Timestamps mixtos: TEXT ISO8601 vs CURRENT_TIMESTAMP | Varias migrations.py |
| No hay soft deletes (deleted_at) | Todas las tablas |
| No hay idempotency keys para pagos/webhooks | billing/ |
| Foreign keys missing en instances → projects | compute/migrations.py |
| `workspace_dir(project_id, name)` ignora project_id | config.py:88-89 |
| Instance.state es enum pero routes devuelven .value | compute/ |

---

## 10. Plan de Acción — Orden de Ejecución

### Fase 1: Código Muerto y Quick Wins (1-2h)
1. Eliminar `ROUTE_REGISTRY` y `ADMIN_MODULES` de main.py
2. Fix `__import__` magic string → import normal
3. Fix `workspace_dir()` parameter misleading
4. Fix `events.py` silent table creation failures

### Fase 2: Partir Archivos Monolíticos (4-6h)
5. Partir `billing/service.py` (1798 → 7 archivos)
6. Partir `billing/routes.py` (833 → 4 sub-routers)
7. Partir `admin/analytics.py` (931 → 4 archivos)
8. Partir `admin/routes.py` (696 → 3 archivos)
9. Partir `storage/routes.py` (588 → separar zar)
10. Partir `workspace/routes.py` (431 → 3 archivos)

### Fase 3: Modularidad (3-4h)
11. Mover AI apps de `addons/` a `engine/ai/`
12. Partir `compute/` en submódulos (instances, pool, hosts)
13. Deduplicar agent auth.py → importar de shared
14. Resolver dependencias circulares via event bus

### Fase 4: CLI (1-2h)
15. Partir `vm/cli/main.py` (897 → subcommands)
16. Migrar urllib → httpx en CLI

### Fase 5: Seguridad (2-3h)
17. JWT_SECRET obligatorio en producción
18. Eliminar default password hash de agent/auth.py
19. Path validation con pathlib en files.py
20. Idempotency keys para billing webhooks

### Fase 6: Tests (4-6h)
21. Tests para compute (instances, pool)
22. Tests para workspace CRUD
23. Tests para deploy pipeline
24. Tests para projects CRUD
25. Tests de integración end-to-end
