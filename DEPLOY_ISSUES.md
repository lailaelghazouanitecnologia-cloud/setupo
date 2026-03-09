# Analisis de Problemas de Deployment — NSO Platform

**Fecha**: 2026-03-09
**Alcance**: Pipeline completo (central server, agent, R2, frontend, config)

---

## CRITICOS — Bloquean el deploy

### 1. Tabla `compute_nodes` referenciada pero no garantizada en deploy

**Archivo**: `nso/engine/deploy/service.py:97-98`

```python
"  SELECT id FROM instances WHERE project_id = ? "
"  UNION SELECT id FROM compute_nodes WHERE project_id = ?"
```

El servicio de deploy hace un UNION con `compute_nodes` para contar deploys diarios, pero si esa tabla no existe aun en la DB (migracion no corrida), el deploy falla con un error SQL. Esto afecta el rate limiting de deploys para planes free.

**Impacto**: Deploy falla con "no such table: compute_nodes" si las migraciones de compute no corrieron.

---

### 2. Credenciales R2 enviadas en plaintext al agent

**Archivo**: `nso/engine/storage/routes.py:118-129`

```python
json={
    "r2_key": r2_key,
    "r2_endpoint": r2_cfg.endpoint,
    "r2_bucket": r2_cfg.bucket,
    "r2_access_key_id": r2_cfg.access_key_id,
    "r2_secret_access_key": r2_cfg.secret_access_key,  # <-- SECRETO
    ...
}
```

Cada deploy envia las credenciales completas de R2 al agent via HTTP (no HTTPS) entre VPSes. Si alguien intercepta el trafico entre el server central y el agent, obtiene acceso completo al storage R2.

**Impacto**: Exposicion de credenciales R2 en transito. Todas las keys de todos los proyectos quedan comprometidas.

---

### 3. Dashboard estatico tiene directorios recursivos `static/static/static/static`

```
client/dashboard/static/          → 8.7MB
client/dashboard/static/static/   → 6.4MB (duplicado!)
```

Hay 4 niveles de anidamiento `static/static/static/static` con archivos duplicados. Esto:
- Infla el tamano del build/deploy innecesariamente
- Puede causar routing incorrecto en nginx
- Sugiere que el build de Next.js se ejecuto multiples veces copiando sobre si mismo

**Impacto**: Deploy mas lento, espacio desperdiciado, posibles conflictos de rutas.

---

### 4. CORS `allow_origins=["*"]` en el Agent

**Archivo**: `vm/agent/main.py:58-63`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

El agent acepta requests de cualquier origen. Combinado con que el agent puede ejecutar comandos (exec.py), escribir archivos, y hacer deploy, esto es un vector de ataque serio si el port 8081 esta expuesto.

---

### 5. Password hardcodeada por defecto en el Agent

**Archivo**: `vm/agent/auth.py:39-44`

```python
_DEFAULT_HASH = _hash_password("zarnlok4123")   # PASSWORD HARDCODEADA!
_PLAIN_HASH = _hash_password(ADMIN_PASSWORD_PLAIN) if ADMIN_PASSWORD_PLAIN else ""

def get_password_hash() -> str:
    return ADMIN_PASSWORD_HASH or _PLAIN_HASH or _DEFAULT_HASH
```

Si `AGENT_ADMIN_PASSWORD` no esta configurada, el agent usa `zarnlok4123` como password. Cualquier persona que conozca este default tiene acceso completo al agent (exec, files, deploy).

**Impacto**: Acceso no autorizado completo al VPS si el env var no esta seteado.

---

### 6. Import roto: `_auto_claim_subdomain` en ship endpoint

**Archivo**: `nso/engine/storage/routes.py:378`

```python
from nso.engine.deploy_agent.tools import _auto_claim_subdomain  # ROTO!
```

La funcion `_auto_claim_subdomain` esta en `nso/engine/deploy_agent/tools/deploy.py`, NO en `__init__.py`. El `__init__.py` no la exporta.

**Impacto**: El endpoint `/ship` crashea con `ImportError` al intentar auto-asignar subdomain despues de cada deploy exitoso.

---

### 7. Deploy SSH usa claves por proyecto — sin verificacion

**Archivo**: `nso/engine/deploy/service.py:150-151`

```python
keys_dir = settings.keys_dir(project_id)
key_path = str(keys_dir / "id_ed25519")
```

Si la clave SSH del proyecto no existe (no se genero al crear la instancia, o se borro), el deploy falla sin un mensaje claro. No hay verificacion previa de que el archivo existe.

---

## ALTOS — Causan fallos intermitentes

### 8. Orchestrator reconciler no autentica contra el agent

**Archivo**: `nso/engine/orchestrator/reconciler.py:586`

```python
headers={},  # TODO: agent auth from instance metadata
```

El reconciler intenta comunicarse con los agents pero no envia token de autenticacion. Esto significa que las reconciliaciones automaticas fallan silenciosamente con 401.

**Impacto**: Auto-scaling, auto-healing, y reconciliacion de estado no funcionan.

---

### 9. Race condition en conexion SQLite compartida

**Archivo**: `nso/shared/db.py:37-41`

```python
async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db
```

Una sola conexion SQLite compartida globalmente. Bajo carga concurrente (multiples deploys simultaneos), esto puede causar:
- `database is locked`
- Escrituras perdidas
- Deadlocks entre las migraciones del lifespan y las del db.py

---

### 10. `_deploy_via_agent` timeout de 300s sin indicador de progreso

**Archivo**: `nso/engine/storage/routes.py:27,114`

El deploy espera hasta 5 minutos una respuesta del agent. Si el agent esta instalando deps (npm install en un VPS de 1GB RAM), puede tardar mas. No hay:
- Streaming de logs
- Webhook de progreso
- Timeout configurable

Si el timeout vence, el estado de la instancia queda en "deploying" para siempre.

---

### 11. Password de BD en infraestructura no se encripta

**Archivo**: `nso/engine/infrastructure/database/service.py:110`

```python
"password_encrypted": db_password,  # TODO: encrypt at rest
```

Las passwords de bases de datos gestionadas se guardan en plaintext en SQLite.

---

### 12. Platform-update hace `git reset --hard` sin verificacion

**Archivo**: `vm/agent/deploy.py:662`

```python
out, code = await _run(f"git fetch origin {req.branch} && git reset --hard origin/{req.branch}")
```

El platform-update del agent hace un hard reset sin verificar si hay cambios locales. Si alguien hizo cambios manuales en el VPS, se pierden sin warning.

---

## MEDIOS — Degradan la experiencia

### 13. Doble sistema de deploy: SSH directo vs Agent/R2

Hay dos caminos de deploy paralelos que no se coordinan:

| Camino | Archivo | Mecanismo |
|--------|---------|-----------|
| SSH directo | `nso/engine/deploy/service.py` | rsync + ssh commands |
| Agent/R2 | `nso/engine/storage/routes.py` | .zar pack → R2 → agent pull |

El primero usa claves SSH directas; el segundo usa la API del agent. Si se mezclan, el estado de la instancia puede quedar inconsistente.

---

### 14. Migraciones se ejecutan dos veces en startup

**Archivo**: `nso/main.py:86-107`

El lifespan ejecuta migraciones de `db.py:_run_module_migrations` (via `init_db`) Y luego ejecuta manualmente `SPEC_MIGRATIONS + EVENTS_MIGRATION + POOL_MIGRATIONS...`. Si alguna migracion no es idempotente, falla al reiniciar.

---

### 15. Agent import `from pipeline import DeployPipeline` puede fallar

**Archivo**: `vm/agent/deploy.py:356`

```python
from pipeline import DeployPipeline
```

Este import solo se ejecuta si existe `deploy.toml` en el proyecto. Si el modulo `pipeline.py` tiene un error de sintaxis o dependencia faltante, el error solo aparece al hacer deploy, no al arrancar el agent.

---

### 16. `self-update` del agent puede matarse a si mismo

**Archivo**: `vm/agent/deploy.py:794-850`

Cuando el agent hace self-update del componente "agent", extrae nuevos archivos sobre si mismo y luego ejecuta `systemctl restart nso-agent`. Si el restart sucede antes de que la respuesta HTTP se envie, el cliente recibe un connection reset.

---

### 17. Variables de entorno en systemd sin escapar

**Archivo**: `nso/engine/deploy/service.py:291-293`

```python
for k, v in (env_vars or {}).items():
    env_lines.append(f"Environment={k}={v}")
```

Los valores de env vars no se escapan para systemd. Si un valor contiene espacios, comillas, o caracteres especiales, el unit file sera invalido.

---

---

## FRONTEND — Problemas de build/deploy del dashboard

### 18. Version de Next.js incompatible entre dashboards

| Dashboard | Next.js |
|-----------|---------|
| `client/dashboard` | `^16.1.6` |
| `client/admin` | `15.1.7` |

Versiones distintas (16.x vs 15.x) causan diferencias en features, Turbopack, y comportamiento de build. Cuando se hace platform-update, ambos se buildean en la misma maquina — las dependencias compartidas pueden conflictuar.

---

### 19. Admin dashboard: JSX config incorrecta en tsconfig

**Archivo**: `client/admin/tsconfig.json`

```json
"jsx": "preserve"   // INCORRECTO para Next.js App Router
```

Deberia ser `"react-jsx"` (como el dashboard principal). Con `preserve`, el SSR y static export no funcionan correctamente.

**Impacto**: Build del admin puede fallar o generar output incorrecto.

---

### 20. API Base hardcodeada con `window.location.origin`

**Archivo**: `client/dashboard/src/lib/api/client.ts:1` y `client/admin/src/lib/api/client.ts:6`

```typescript
const API_BASE = typeof window !== "undefined" ? window.location.origin : "";
```

No hay variable de entorno (`NEXT_PUBLIC_API_BASE`). Si el frontend se sirve desde un dominio diferente al API (ej: CDN, subdomain distinto), todas las llamadas API fallan.

---

### 21. Script `export` copia recursivamente sobre si mismo

**Archivo**: Ambos `package.json`

```json
"export": "next build && cp -r out/* static/"
```

Cada vez que se ejecuta `npm run export`, copia `out/` a `static/`. Si ya existe contenido en `static/`, se acumula — esto explica los directorios recursivos `static/static/static/static` (issue #3).

**Impacto**: Cada build duplica el contenido. Debe hacer `rm -rf static && ...` antes.

---

### 22. Admin host check en frontend es fragil

**Archivo**: `client/dashboard/src/components/dashboard/dashboard-layout.tsx:139`

```typescript
window.location.hostname.startsWith("sonfazt")
```

Solo verifica el prefijo del hostname. Un dominio como `sonfazt-fake.nso.dev` pasaria el check. Deberia comparar con el hostname exacto.

---

## BAJOS — Mejoras recomendadas

### 23. R2Client no hace retry en fallos de red
- `nso/engine/storage/service.py` — Un fallo transitorio de R2 (timeout, 5xx) aborta todo el deploy.

### 24. No hay health check del agent antes de deployar
- El server asume que el agent responde. Si el agent esta caido, el deploy falla con un error generico de conexion.

### 25. Logs de deploy limitados a 500 lineas en agent
- `vm/agent/deploy.py:33` — `MAX_LOG_LINES = 500`. Si un build genera mucho output, se trunca y se pierde informacion de debug.

### 26. Snapshots no comprimen
- `vm/agent/deploy.py:147` — `shutil.copytree` copia archivos sin comprimir. En un VPS de 25GB, 5 snapshots de un proyecto grande pueden llenar el disco.

### 27. `openai>=1.0.0` en requirements.txt sin version fija
- `requirements.txt:9` — Puede introducir breaking changes en produccion.

### 28. No hay `.env.example` para frontends
- Los dashboards no tienen configuracion de entorno documentada. No se puede setear Stripe keys, API base, etc. en build time.

---

## Resumen de prioridades

| Prioridad | Cant | Accion inmediata |
|-----------|------|-----------------|
| CRITICO | 7 | Fix import roto en ship, password hardcodeada, tabla compute_nodes, credenciales R2, static dirs |
| ALTO | 5 | Auth del reconciler, timeout de deploy, race condition SQLite |
| MEDIO | 5 | Unificar paths de deploy, fix migraciones duplicadas |
| FRONTEND | 5 | Next.js version mismatch, JSX config, export script recursivo, API base hardcoded |
| BAJO | 6 | Retry R2, health check pre-deploy, pin versions |
