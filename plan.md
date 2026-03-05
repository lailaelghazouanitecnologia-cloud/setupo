# Plan: Conexión SSH + NSO CLI Download

## Contexto actual

- Las instancias se crean via Vultr API con cloud-init
- SSH key (ed25519) se genera por proyecto en `/opt/nso/data/keys/{project_id}/`
- Se sube la pubkey a Vultr y se inyecta en el VPS
- **No hay forma para el usuario de descargar la key privada**
- **No hay forma de descargar el CLI (nso) desde el dashboard**
- Todo acceso va por Agent HTTP (:8081) — no SSH expuesto al usuario

## Lo que se necesita

### 1. Conexión SSH a instancias

**Opción A: Via Agent (actual — ya funciona)**
- El agent ya expone `/exec/` para ejecutar comandos
- El dashboard ya tiene terminal integrado
- No necesita SSH directo

**Opción B: SSH directo (nuevo)**
- Permitir al usuario descargar la private key para SSH manual
- Nuevo endpoint: `GET /api/projects/{pid}/ssh-key`
- El dashboard muestra el comando: `ssh -i ~/.nso/key root@{ip}`

**Recomendación**: Mantener Agent como método principal, añadir SSH key download como opción avanzada.

### 2. NSO CLI — Empaquetado

**Estado actual:**
- `cli/` tiene 3 archivos: `main.py`, `client.py`, `output.py`
- `nso` es un wrapper Python de 12 líneas
- No hay `pyproject.toml` ni `setup.py`
- Dependencias: solo `httpx` y `rich` (las de runtime)

**Plan de empaquetado:**

```
Paso 1: Crear pyproject.toml
  - name: "nso-cli"
  - entry_point: nso = cli.main:main
  - dependencies: httpx, rich

Paso 2: Crear binarios pre-built (PyInstaller)
  - nso-linux-x86_64
  - nso-macos-arm64
  - nso-macos-x86_64
  - nso-windows.exe

Paso 3: Subir a R2
  - _cli/latest/nso-linux-x86_64
  - _cli/latest/nso-macos-arm64
  - _cli/latest/nso-windows.exe
  - _cli/latest/install.sh (installer script)
```

### 3. Endpoint de descarga del CLI

**Nuevo archivo: `server/routes/cli.py`**

```
GET /api/cli/install          — Script de instalación (curl | sh)
GET /api/cli/download?os=     — Binary descargable (linux/macos/windows)
GET /api/cli/version          — Última versión disponible
```

El install script:
```bash
#!/bin/sh
# curl -fsSL https://nso.dev/api/cli/install | sh
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
curl -fsSL "https://nso.dev/api/cli/download?os=${OS}&arch=${ARCH}" -o /usr/local/bin/nso
chmod +x /usr/local/bin/nso
echo "NSO CLI installed. Run: nso login"
```

### 4. Dashboard — Post-login CLI download

**Modificar: `client/dashboard/src/components/dashboard/settings-panel.tsx`**

Añadir nueva sección "CLI & Access":

```
┌─────────────────────────────────────────────────┐
│  CLI & Access                                    │
│                                                  │
│  Install NSO CLI:                                │
│  ┌─────────────────────────────────────────────┐ │
│  │ curl -fsSL https://nso.dev/api/cli/install  │ │
│  │ | sh                                   [📋] │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  Or download directly:                           │
│  [Linux x86_64] [macOS ARM] [macOS Intel] [Win]  │
│                                                  │
│  Quick login:                                    │
│  ┌─────────────────────────────────────────────┐ │
│  │ nso login -e your@email.com           [📋]  │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  API Key (for this project):                     │
│  sk_live_xxxx...xxxx              [Rotate] [📋]  │
│                                                  │
│  SSH Access (advanced):                          │
│  ┌─────────────────────────────────────────────┐ │
│  │ ssh -i ~/.nso/key root@{ip}           [📋]  │ │
│  └─────────────────────────────────────────────┘ │
│  [Download SSH Key]                              │
└─────────────────────────────────────────────────┘
```

### 5. Flujo completo del usuario

```
1. Usuario visita nso.dev
2. Se registra o hace login
3. Ve el dashboard con proyecto auto-creado ("main")
4. Va a Settings → CLI & Access
5. Copia el comando de instalación
6. En su terminal: curl -fsSL https://nso.dev/api/cli/install | sh
7. nso login -e su@email.com --password xxx
8. nso inst create --label prod --region mad --domain app.example.com
9. nso ship mi-workspace inst_xxx
10. (Opcional) Descarga SSH key para acceso directo
```

## Orden de implementación

### Fase 1: CLI Package (backend)
1. Crear `pyproject.toml` para nso-cli
2. Crear `server/routes/cli.py` con endpoints de descarga
3. Crear `install.sh` template
4. Montar ruta en `server/main.py`

### Fase 2: Dashboard UI
5. Añadir sección "CLI & Access" en settings-panel.tsx
6. Endpoint SSH key download: `GET /api/projects/{pid}/ssh-key`
7. Mostrar API key del proyecto actual
8. Botones de descarga con detección de OS

### Fase 3: Landing page
9. Añadir sección de descarga en la landing (pre-login)
10. Mostrar `curl | sh` prominente
11. Quick start guide

### Fase 4: Build & Deploy
12. Build CLI binaries (CI/CD o manual)
13. Subir binaries a R2
14. Deploy dashboard actualizado
15. Test end-to-end

## Archivos a crear/modificar

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `pyproject.toml` | CREAR | Package metadata para nso-cli |
| `server/routes/cli.py` | CREAR | Endpoints de descarga e instalación |
| `server/main.py` | MODIFICAR | Montar router de cli |
| `client/dashboard/.../settings-panel.tsx` | MODIFICAR | Sección CLI & Access |
| `server/routes/projects.py` | MODIFICAR | Endpoint para ver API key (hash→partial) |
| `server/routes/instances.py` | MODIFICAR | Endpoint SSH key download |
| `client/dashboard/src/app/page.tsx` | MODIFICAR | Landing con install command |
