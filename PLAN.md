# Plan: nso-ready — Pre-compiled Instant Boot System

## Problema

El cloud-init actual tarda **~6-8 min** cuando no hay imagen pre-compilada:
- `git clone` (~30s)
- `pip install` requirements (~60s)
- `curl nodesource + apt install nodejs` (~30s)
- `npm install + build` dashboard (~120s)
- `npm install + build` admin (~90s)
- SSL + servicios (~60s)

El cloud-init **ya tiene** detección de nso-ready (líneas 344-376), pero **no existe**
un mecanismo para crear/subir la imagen al bucket `nso-ready`.

## Solución: 2 niveles de pre-compilado

### Nivel 1: Sistema NSO (bucket `nso-ready`)

Pre-compilar el platform completo y guardarlo como .zar en R2.

**R2 layout en `nso-ready`:**
```
system/latest.zar
system/v{version}.zar
system/manifest.json          # { version, hash, built_at, git_branch, git_commit }
```

**Contenido del system .zar:**
```
.zar-manifest.json
files/
  server/                     # Código Python del server
  instance/                   # Código del agent
  client/dashboard/static/    # Dashboard pre-built (next export)
  client/admin/static/        # Admin pre-built (next export)
  requirements.txt            # Para pip install en el VPS
  common/                     # Shared utilities
```

**Flujo boot con nso-ready (ya implementado en cloud-init):**
1. apt install packages
2. Descargar `system/latest.zar` de `nso-ready` ← **ya existe en cloud-init**
3. Extraer a `/opt/nso/`
4. Crear venv + pip install (~30s)
5. Arrancar servicios + SSL
6. **Tiempo estimado: ~2 min** (vs 6-8 actual)

### Nivel 2: Apps de usuario (bucket `nso`)

Los usuarios pre-compilan su app para que nuevas instancias arranquen con la app lista.

**R2 layout en `nso`:**
```
{project_id}/_ready/{workspace}/latest.zar
{project_id}/_ready/{workspace}/v{version}.zar
{project_id}/_ready/{workspace}/manifest.json
```

**Flujo boot con app-ready:**
1. Boot rápido con nso-ready (nivel 1)
2. Cloud-init detecta `APP_READY_KEY` en env
3. Descarga app .zar de R2 → extrae a `/opt/app/`
4. Instala deps + arranca servicio app
5. **Instancia lista con app en ~3 min total**

---

## Implementación — 8 tareas

### Tarea 1: CLI command `nso system build`

**Archivo:** `cli/main.py`

Nuevo comando que:
1. Ejecuta `npm run build` en `client/dashboard/` y `client/admin/`
2. Empaqueta como .zar: `server/`, `instance/`, `client/*/static/`, `requirements.txt`, `common/`
3. Sube a `nso-ready` bucket como `system/v{version}.zar` + `system/latest.zar`
4. Actualiza `system/manifest.json`

```
nso system build                # Build + pack + push
nso system build --skip-build   # Solo pack + push (si dashboards ya están built)
nso system status               # Muestra versión actual en R2
```

**Dependencias:** Necesita R2 credentials (del .env del server o CLI config).

### Tarea 2: Admin API endpoint `/api/admin/system/build`

**Archivo:** `server/routes/admin.py`

Nuevo endpoint admin-only que ejecuta el build desde el server:

```
POST /api/admin/system/build
  → { "version": "20260303.200000", "size_mb": 12.5, "uploaded": true }

GET /api/admin/system/status
  → { "version": "20260303.200000", "built_at": "...", "size_mb": 12.5 }
```

**Implementación:**
- Nuevo módulo `server/core/system_build.py`:
  - `async def build_system_image(skip_dashboards=False) -> SystemBuildResult`
  - Usa `packer.pack()` internamente pero con paths custom
  - Sube con `R2Client` al bucket `nso-ready`

### Tarea 3: Adaptar `packer.py` para system builds

**Archivo:** `server/core/zar/packer.py`

Agregar función `pack_system()`:

```python
def pack_system(
    repo_root: str,              # Raíz del repo (donde está server/, instance/, etc.)
    version: str | None = None,
    git_branch: str = "main",
    git_commit: str = "",
) -> tuple[bytes, dict]:
    """Pack NSO system files into a .zar for nso-ready bucket."""
    # Include: server/, instance/, client/*/static/, requirements.txt, common/
    # Exclude: node_modules, .git, __pycache__, venv, tests/, cli/, doc/
```

No modifica `pack()` existente — función separada.

### Tarea 4: Adaptar `storage.py` para nso-ready bucket

**Archivo:** `server/core/zar/storage.py`

Agregar métodos al `R2Client`:

```python
async def upload_system(self, version: str, zar_bytes: bytes) -> str:
    """Upload system .zar to nso-ready bucket."""
    # Upload versioned: system/v{version}.zar
    # Upload latest: system/latest.zar
    # Update manifest: system/manifest.json

async def get_system_status(self) -> dict | None:
    """Get current system image info from nso-ready."""
    # Download and parse system/manifest.json

async def upload_app_ready(self, project_id, workspace, version, zar_bytes) -> str:
    """Upload user app .zar to _ready/ prefix in main bucket."""
    # Upload: {project_id}/_ready/{workspace}/v{version}.zar
    # Upload: {project_id}/_ready/{workspace}/latest.zar
    # Update manifest

async def get_app_ready_status(self, project_id, workspace) -> dict | None:
    """Get app-ready image info."""
```

Estos métodos usan `R2_READY_BUCKET` para system y `R2_BUCKET` para apps.

### Tarea 5: Nuevo route para app-ready

**Archivo:** `server/routes/zar.py`

Nuevos endpoints:

```
POST /api/projects/{pid}/zar/{name}/freeze
  → Pack workspace + push a _ready/ prefix
  → { "version": "...", "r2_key": "...", "size_mb": ... }

GET /api/projects/{pid}/zar/{name}/freeze/status
  → { "version": "...", "built_at": "...", "size_mb": ... }

DELETE /api/projects/{pid}/zar/{name}/freeze
  → Elimina la imagen pre-compilada
```

### Tarea 6: Cloud-init — app-ready integration

**Archivo:** `server/base/cloud-init.yaml`

Agregar después del bloque nso-ready (línea ~400):

```bash
# ── App pre-built image ──
APP_READY_KEY="${APP_READY_KEY:-}"
if [ -n "$APP_READY_KEY" ]; then
  echo "[nso] Downloading pre-built app from R2..."
  python3 /opt/nso/deploy/r2-download.py "$R2_BUCKET" "$APP_READY_KEY" "/tmp/app-ready.zar"
  if [ $? -eq 0 ]; then
    echo "[nso] Extracting app..."
    mkdir -p /opt/app
    tar xzf /tmp/app-ready.zar -C /opt/app --strip-components=1
    rm /tmp/app-ready.zar
    APP_READY=1
  fi
fi
```

Y en `get_cloud_init()` (types.py):
- Nuevo placeholder `{{APP_READY_KEY}}`
- Se llena desde `instance.metadata.app_ready_key` si existe

### Tarea 7: Instance creation — source_type enhancements

**Archivo:** `server/core/instances/manager.py` + `types.py`

Cuando `source_type == "repository"` y existe una imagen `_ready/` para ese workspace:
- Pasar `APP_READY_KEY` al cloud-init
- La instancia arranca con la app pre-compilada
- Fallback a git clone si no hay imagen

Nuevo source_type: `"ready"` — usa directamente la imagen frozen.

**Archivo:** `server/core/models.py`

```python
class CreateInstanceRequest(BaseModel):
    # ... existing fields ...
    source_type: Optional[str] = None  # "repository" | "zar" | "folder" | "ready"
    app_ready_key: Optional[str] = None  # R2 key for pre-built app
```

### Tarea 8: Dashboard UI updates

**Archivo:** `client/dashboard/src/components/dashboard/instances-panel.tsx`

1. **Create form**: Nuevo source_type `"ready"` con selector de workspace frozen
2. **Instance card**: Mostrar badge "ready" cuando usa imagen pre-compilada
3. **Instance detail grid**: Mostrar "Source: pre-built (workspace-name v20260303)"

---

## Orden de implementación

```
Tarea 3 (packer.py)  ─┐
Tarea 4 (storage.py) ─┤─→ Tarea 2 (admin API) ─→ Tarea 1 (CLI)
                       │
                       └─→ Tarea 5 (freeze routes) ─→ Tarea 6 (cloud-init) ─→ Tarea 7 (instance creation) ─→ Tarea 8 (UI)
```

Tareas 3+4 son independientes y se hacen primero (backend).
Luego bifurca: sistema (2→1) y apps (5→6→7→8).

---

## Build inicial del sistema

Después de implementar, el primer build se hace:

```bash
# Opción 1: CLI (desde máquina con el repo)
nso system build

# Opción 2: Admin API (desde el server en producción)
curl -X POST https://nso.dev/api/admin/system/build \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Esto sube `system/latest.zar` (~12-15MB) a `nso-ready`.
Las siguientes instancias creadas lo descargarán automáticamente.

---

## Resultado esperado

| Escenario | Antes | Después |
|-----------|-------|---------|
| Nueva instancia (sin nso-ready) | ~6-8 min | ~6-8 min (fallback) |
| Nueva instancia (con nso-ready) | N/A | ~2 min |
| Nueva instancia + app frozen | N/A | ~3 min |
| Deploy app a instancia existente | ~30s | ~30s (sin cambio) |
