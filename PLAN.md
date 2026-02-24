# Plan: Workspace Manager + Complete API + Theme System + Redesign

## 1. Arquitectura del Sistema de Workspaces

### Concepto
Un workspace = un directorio en `/opt/mms/workspaces/`. Tres tipos:
- **base**: El repo setupo mismo (siempre disponible, nunca se borra)
- **git**: Repo clonado desde URL
- **custom**: Directorio vacío creado por el usuario

Cada workspace tiene un archivo opcional `.workspace.json`:
```json
{
  "type": "git|custom|base",
  "created_at": "2024-...",
  "repo": "https://github.com/...",
  "branch": "main",
  "description": "My project"
}
```

### Flujo de uso
1. El usuario ve la lista de workspaces
2. Click en un workspace → se convierte en el contexto activo
3. El sidebar muestra: Files, Services, Terminal - todo scoped al workspace activo
4. Se puede crear un workspace vacío ("New Workspace") o clonar un repo

---

## 2. Backend API Completa (accesible via curl)

### Workspaces
```
GET    /api/workspaces                     → Lista todos los workspaces
POST   /api/workspaces                     → Crear workspace (vacío o clone)
         body: { "name": "mi-proyecto", "type": "custom" }
         body: { "name": "mi-repo", "type": "git", "repo": "...", "branch": "main" }
GET    /api/workspaces/{name}              → Detalles de un workspace
DELETE /api/workspaces/{name}              → Eliminar workspace (no base)
POST   /api/workspaces/{name}/pull         → Git pull (solo git)
```

### File System (scoped a workspace)
```
GET    /api/workspaces/{name}/fs?path=src  → Listar directorio relativo
GET    /api/workspaces/{name}/fs/read?path=src/app.py → Leer archivo
POST   /api/workspaces/{name}/fs/write     → Escribir archivo
         body: { "path": "src/app.py", "content": "..." }
POST   /api/workspaces/{name}/fs/mkdir     → Crear directorio
         body: { "path": "src/utils" }
DELETE /api/workspaces/{name}/fs?path=src/old.py → Eliminar archivo/dir
POST   /api/workspaces/{name}/fs/move      → Mover/renombrar
         body: { "from": "old.py", "to": "new.py" }
```

### Services (scoped a workspace)
```
GET    /api/services                       → Todos los servicios (global)
POST   /api/services                       → Crear servicio
         body: { "name": "api", "command": "python app.py", "workspace": "mi-proyecto", "port": 3000 }
POST   /api/services/{name}/stop           → Parar
POST   /api/services/{name}/restart        → Reiniciar
DELETE /api/services/{name}                → Eliminar
GET    /api/services/{name}/logs?tail=100  → Logs
```

### System (para programación live)
```
POST   /api/system/restart                 → Reiniciar el servidor principal (port 8000)
POST   /api/system/snapshot                → Guardar estado actual como backup
POST   /api/system/restore                 → Restaurar desde último snapshot
GET    /api/system/info                    → Info del sistema (uptime, cpu, mem, disk)
POST   /api/system/build-frontend          → npm run build del frontend activo
POST   /api/system/deploy                  → Copiar build a dashboard/static
```

### Terminal
```
WS     /ws/shell?token=...                 → Shell PTY (ya existe)
WS     /ws/shell?token=...&cwd=/opt/mms/workspaces/mi-proyecto → Shell en workspace
```

---

## 3. Sistema de Fallback (Puerto 8081)

### Estructura
- **Puerto 8000**: Servidor principal (desarrollo activo)
- **Puerto 8081**: Servidor base estable (nunca se toca)

### Implementación
- Nuevo servicio systemd: `mms-base.service`
- Corre uvicorn con una copia estática del código en `/opt/mms/base-server/`
- Sirve una versión mínima del dashboard + API básica
- Nginx ruta: `zarnetti.com/safe` → puerto 8081

### API del servidor base (mínima)
```
GET    /api/health
POST   /api/auth/login
GET    /api/fs/list, /api/fs/read
POST   /api/fs/write
POST   /api/system/restart    → Reinicia el servidor principal (8000)
POST   /api/system/restore    → Copia base-server/ → opt/mms/ y reinicia
WS     /ws/shell              → Terminal de emergencia
```

---

## 4. Theme System

### CSS Variables por tema
Cada tema define un set completo de CSS variables. Se guardan como JSON en `/opt/mms/themes/`.

### Temas incluidos
1. **Zed Dark** (default) - Fondo cálido oscuro, acentos azul/lavanda
2. **Zed Light** - Versión clara
3. **Midnight** - Ultra oscuro, acentos neón

### Paleta Zed Dark (default)
```css
--bg-base:     #1e1e2e    /* Fondo principal */
--bg-surface:  #232336    /* Cards, panels */
--bg-overlay:  #2a2a3d    /* Dialogs, dropdowns */
--bg-subtle:   #181825    /* Sidebar, headers */
--border:      rgba(255,255,255, 0.06)
--border-focus: rgba(137, 180, 250, 0.4)

--text:        #cdd6f4    /* Texto principal */
--text-muted:  #6c7086    /* Texto secundario */
--text-subtle: #45475a    /* Placeholders */

--accent:      #89b4fa    /* Azul principal */
--accent-hover:#74c7ec    /* Hover azul */
--accent-muted: rgba(137, 180, 250, 0.12)
--lavender:    #b4befe    /* Violeta/lavanda */
--green:       #a6e3a1    /* Éxito */
--yellow:      #f9e2af    /* Warning */
--red:         #f38ba8    /* Error/destructive */
--peach:       #fab387    /* Info alternativo */
```

### Aplicación
- Theme guardado en localStorage
- CSS variables se aplican en `:root`
- Un `ThemeProvider` React con context para cambiar entre temas

---

## 5. Rediseño Frontend (Zed + Notion)

### Principios de diseño
1. **Densidad**: 20% más compacto - menos padding, font sizes más pequeños
2. **Composición**: Layout basado en paneles, no cards sueltas
3. **Tipografía**: Inter para UI, JetBrains Mono para código. Jerarquía clara.
4. **Color**: Warm dark, acentos sutiles, sin colores chillones
5. **Bordes**: Mínimos. Usar diferencias sutiles de fondo en vez de bordes
6. **Iconos**: Lucide 14-16px, stroke-width 1.5, nunca decorativos
7. **Espaciado**: Consistente 4px grid system
8. **Animaciones**: Sutiles, rápidas (150ms), solo donde aportan

### Layout principal
```
┌─────────────────────────────────────────────────┐
│ [workspace-selector] ──────── [user] [theme] [⚙]│  ← Header 32px
├──────┬──────────────────────────────────────────┤
│      │                                          │
│  nav │   content area                           │
│      │                                          │
│ dash │                                          │
│ svc  │                                          │
│ files│                                          │
│ term │                                          │
│      │                                          │
│      │                                          │
├──────┤                                          │
│status│                                          │
└──────┴──────────────────────────────────────────┘
  48px            rest
```

### Sidebar (48px collapsed, 180px expanded)
- Solo iconos cuando está colapsado (como Zed)
- Hover para ver tooltip con nombre
- Active state: línea vertical azul a la izquierda del icono
- Navegación: Dashboard, Services, Files, Terminal
- Footer: status dot + versión

### Workspace Selector (en header)
- Dropdown con búsqueda
- Muestra: [icon] nombre-workspace  [branch si git]
- Opciones: "New workspace", "Clone repo"
- Cambiar workspace cambia el contexto de Files, Terminal, Services

### Páginas rediseñadas

#### Dashboard
- Grid de métricas compacto (no cards grandes, sino inline stats)
- Lista de servicios activos como tabla compacta
- Quick actions: new service, new workspace
- Estilo Notion: bloques de contenido con títulos sutiles

#### Services
- Tabla limpia, sin cards
- Columnas: Status dot, Name, Command (mono), Port, PID, Actions
- Row click → expand logs inline
- Create service: inline form o small modal

#### Files
- Split panel: tree a la izquierda, editor a la derecha
- Tree: folders con indent, no icons excesivos
- Editor: textarea con line numbers, syntax highlighting básico
- Breadcrumb compacto arriba del editor

#### Terminal
- Full height, sin header innecesario
- Tab bar si múltiples terminales en el futuro

---

## 6. Archivos a Modificar/Crear

### Backend (Python)
1. `server/routes/workspaces.py` → Reescribir completamente
2. `server/routes/fs.py` → Agregar scope por workspace + move
3. `server/routes/services.py` → Agregar campo workspace
4. `server/routes/system.py` → NUEVO: restart, snapshot, restore, build, deploy
5. `server/main.py` → Registrar nuevas rutas
6. `server/routes/terminal.py` → Soporte cwd por workspace

### Frontend
7. `src/index.css` → Nueva paleta Zed dark
8. `src/lib/api.ts` → Nuevos endpoints workspace-scoped
9. `src/lib/theme.ts` → NUEVO: theme provider + temas
10. `src/App.tsx` → Nuevo layout: header + sidebar compacto + content
11. `src/pages/Dashboard.tsx` → Rediseño compacto Notion-style
12. `src/pages/Services.tsx` → Tabla limpia
13. `src/pages/Workspaces.tsx` → ELIMINAR (se integra en selector de header)
14. `src/pages/Files.tsx` → Split panel con tree
15. `src/pages/Terminal.tsx` → Full height, minimal chrome
16. `src/pages/Login.tsx` → Estilo Zed minimal
17. `src/components/WorkspaceSelector.tsx` → NUEVO
18. `src/components/ThemeSwitcher.tsx` → NUEVO

### Deploy
19. `deploy/nginx.conf` → Agregar ruta /safe → 8081
20. `deploy/mms-base.service` → NUEVO: servicio base en puerto 8081
21. `server/base_server.py` → NUEVO: servidor mínimo para fallback

---

## 7. Orden de implementación

### Fase 1: Backend API completa
1. Reescribir `workspaces.py` (custom + git + base)
2. Agregar `system.py` (restart, snapshot, restore)
3. Actualizar `fs.py` (scope por workspace + move)
4. Actualizar `services.py` (campo workspace)
5. Actualizar `terminal.py` (cwd por workspace)
6. Actualizar `main.py`

### Fase 2: Servidor base/fallback
7. Crear `base_server.py`
8. Crear `mms-base.service`
9. Actualizar `nginx.conf`

### Fase 3: Frontend redesign
10. Theme system (CSS + provider)
11. Layout principal (App.tsx + WorkspaceSelector)
12. Dashboard
13. Services
14. Files
15. Terminal
16. Login

### Fase 4: Build y deploy
17. Build frontend
18. Deploy a dashboard/static
19. Reiniciar servicio
