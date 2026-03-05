# Plan de Refactoring — Frontend NSO Dashboard + Admin

## Resumen del Análisis

Se analizaron **13,000+ líneas** de código frontend en 2 dashboards (main + admin).
Se encontraron **80+ problemas** categorizados en 12 áreas.

---

## Fase 1: Bugs Críticos y CSS Rotos (Prioridad ALTA)

### 1.1 CSS Variables Indefinidas
**Archivos:** `client/dashboard/src/app/globals.css`
- `--sidebar-bg` usada en líneas 281, 1401, 1461 pero **nunca definida**. Debe ser `--sidebar-background`.
- Resultado: esos elementos caen a `inherit` silenciosamente, rompiendo el layout en light mode.

### 1.2 Variables de Color Duplicadas Entre Temas
- `--color-yellow`, `--color-green`, `--color-teal`, `--color-red`, `--color-blue`, `--color-purple` se definen idénticamente en `:root` y `.dark`. Son theme-independent → definir una sola vez en `:root`.

### 1.3 Catch Blocks Silenciosos en API Client
**Archivo:** `client/dashboard/src/lib/api/client.ts`
- Línea 56: `catch {}` en `parseErrorText()` — traga errores de parsing JSON.
- Línea 91: `catch {}` en login agent auth — usuario queda autenticado en API pero no en agent, sin aviso.

### 1.4 Page Reload en 401 (Token Expirado)
**Archivo:** `client/dashboard/src/lib/api/client.ts` línea 43
- `window.location.reload()` pierde todo estado no guardado del usuario.
- Cambiar por logout limpio + redirect a login sin reload.

### 1.5 Active Project No Se Restaura
**Archivo:** `client/dashboard/src/stores/dashboard-store.ts`
- `setActiveProject()` guarda ID en localStorage (`nso_active_project`).
- Pero al iniciar, **nunca se lee**. El proyecto activo se pierde entre sesiones.

---

## Fase 2: Extraer Utilidades Compartidas (Eliminar Duplicación)

### 2.1 Crear `client/dashboard/src/lib/format.ts`
Funciones duplicadas en 6+ archivos:
- `formatSize(bytes)` — duplicada en deploy-panel, instances-panel, workspaces-panel, admin-panel
- `timeAgo(date)` — duplicada en loadbalancer-panel, orchestrator-panel, admin-panel
- `fmt(value)` / `formatNum(n)` — duplicada 5 veces en admin-panel
- `stateColor(state)` / `stateBadgeClass(state)` — duplicada en instances-panel, admin-panel

### 2.2 Crear `client/dashboard/src/lib/terminal-styles.ts`
Colores hardcodeados del terminal duplicados:
- `deploy-panel.tsx` líneas 705-706: `#0d1117`, `#c9d1d9`, `#484f58`
- `instances-panel.tsx` líneas 700-731: mismos colores
- Centralizar como CSS variables o constantes exportadas.

### 2.3 Crear constantes de colores inline
**Problema:** 50+ colores hardcodeados en JSX inline styles en lugar de usar CSS variables.
- `addons-panel.tsx` líneas 292-298: `rgba(2,184,204,0.1)` → `var(--color-teal-10)`
- `admin-panel.tsx` líneas 1210, 1691: `var(--color-green, green)` fallbacks inline

---

## Fase 3: Partir Componentes Monolíticos

### 3.1 Dashboard Principal — Componentes Grandes

| Archivo | Líneas | Acción |
|---------|--------|--------|
| `billing-panel.tsx` | 1272 | Separar en `BillingOverview`, `BillingPlans`, `BillingInvoices`, `BillingWallets`, `BillingCoupons` |
| `admin-panel.tsx` | 989 | Separar en `AdminOverview`, `AdminUsers`, `AdminAnalytics`, `AdminFraud`, `AdminLedger` |
| `instances-panel.tsx` | 972 | Extraer `TerminalPanel`, `FilesPanel`, `CreateInstanceForm`, `ServicesTab` |
| `addons-panel.tsx` | 804 | Extraer `PluginDetailView`, `ConnectorDetailView`, `MarketplaceCard` |
| `deploy-panel.tsx` | 776 | Extraer `DeployConfig`, `ZarVersions`, `DeployLogs` |

### 3.2 Admin Dashboard — Componente Masivo

**`client/admin/src/components/admin-panel.tsx`** — **2,802 líneas en un solo archivo**.

Debe separarse en:
```
client/admin/src/components/
├── admin-panel.tsx          (router de tabs, <200 líneas)
├── tabs/
│   ├── overview-tab.tsx
│   ├── cashflow-tab.tsx
│   ├── users-tab.tsx
│   ├── user-detail.tsx
│   ├── analytics-tab.tsx
│   ├── fraud-tab.tsx
│   ├── ledger-tab.tsx
│   ├── infra-tab/
│   │   ├── index.tsx
│   │   ├── instances-view.tsx
│   │   ├── database-view.tsx
│   │   └── storage-view.tsx
│   ├── orchestrator-tab/
│   │   ├── index.tsx
│   │   ├── overview.tsx
│   │   ├── nodes.tsx
│   │   ├── builds.tsx
│   │   └── alerts.tsx
│   ├── loadbalancer-tab/
│   │   ├── index.tsx
│   │   ├── overview.tsx
│   │   ├── pools.tsx
│   │   ├── rules.tsx
│   │   └── nginx.tsx
│   └── z86-tab/
│       ├── index.tsx
│       ├── overview.tsx
│       ├── buckets.tsx
│       ├── files.tsx
│       ├── terminal.tsx
│       └── secrets.tsx
```

---

## Fase 4: API Client — Robustez

### 4.1 Separar API Client por Contexto
**Problema actual:** `apiCall()` default usa `nso_token` (agent), `centralApi()` wrapper usa `nso_api_token`.
Fácil confundir cuál usar.

**Solución:**
```typescript
// client/dashboard/src/lib/api/agent-client.ts
export function agentCall<T>(path: string, options?: RequestInit): Promise<T>

// client/dashboard/src/lib/api/central-client.ts
export function centralCall<T>(path: string, options?: RequestInit): Promise<T>
```

### 4.2 Añadir Request Timeout
- Ninguna llamada API tiene timeout configurado.
- `fetch()` puede colgar indefinidamente si el servidor no responde.
- Añadir `AbortController` con timeout de 30s default.

### 4.3 Añadir Request Retry con Backoff
- Para errores transitorios (503, network errors).
- 3 reintentos con backoff exponencial (1s, 2s, 4s).

### 4.4 Logout Limpio en vez de Reload
- Actual: `window.location.reload()` en 401.
- Nuevo: emit logout event → store.logout() → show login page sin perder contexto.

### 4.5 Agent Auth Warning
- Login intenta obtener agent JWT (línea 91).
- Si falla, silenciosamente continúa.
- Mostrar warning: "Agent no disponible — funciones de deploy limitadas".

---

## Fase 5: Store — Separar Concerns

### 5.1 Separar Auth Store de Project Store
**Actual:** Un solo `dashboard-store.ts` con auth + projects + workspaces + theme.

**Nuevo:**
```typescript
// stores/auth-store.ts — token, user, theme
// stores/project-store.ts — projects, workspaces, active selections
```

### 5.2 Restaurar Active Project al Iniciar
- Leer `localStorage.getItem("nso_active_project")` en init.
- Hacer fetch del proyecto para validar que existe.
- Si no existe, limpiar la referencia.

### 5.3 Limpiar Token Inconsistency
- `setToken()` escribe solo `nso_api_token`.
- `getInitialToken()` lee `nso_api_token || nso_token`.
- Logout limpia ambos.
- Inconsistencia: ¿qué pasa si solo existe `nso_token`?

---

## Fase 6: Type Safety

### 6.1 Eliminar `any` Types
Instancias encontradas:
- `client.ts`: `catch (err: any)` × 20+ instancias → usar `unknown`
- `admin-panel.tsx`: `useState<any>(null)` × 10+ instancias → definir interfaces
- `addons-panel.tsx`: `{f: any}` → `FileObject`
- `instances-panel.tsx`: `useState<any[]>` → `FileItem[]`

### 6.2 Completar Interfaces de API Response
**Archivo:** `client/dashboard/src/types/dashboard.ts` (solo 61 líneas)
Falta: ProjectResponse, WorkspaceResponse, DeployStatus, AddonCatalogItem, BillingPlan, etc.

### 6.3 Unificar Secret Types
- `Secret` en dashboard.ts: `{ key, value?, masked }`
- `AgentSecret` en client.ts: `{ key, value, bucket }`
- Crear un solo tipo con campos opcionales.

---

## Fase 7: Inline Styles → CSS Classes

### 7.1 Componentes con Exceso de Inline Styles
| Componente | Líneas con inline styles | Acción |
|------------|--------------------------|--------|
| `addons-panel.tsx` | 50+ líneas (MarketplaceCard) | Mover a `.marketplace-card` en CSS |
| `instances-panel.tsx` | 40+ líneas (forms, badges) | Mover a `.inst-form`, `.inst-badge` |
| `secrets-panel.tsx` | 30+ líneas (scope selector) | Mover a `.scope-selector` en CSS |
| `dashboard-layout.tsx` | 20+ líneas (error boundary) | Mover a `.error-boundary` en CSS |
| `admin-panel.tsx` | 100+ líneas (cards, tables, modals) | Mover a admin globals.css |

### 7.2 Terminal Styles
Hardcodeados en JSX:
```tsx
style={{ background: "#0d1117", color: "#c9d1d9" }}
```
→ Crear clases CSS:
```css
.terminal-panel {
  background: var(--terminal-bg, #0d1117);
  color: var(--terminal-fg, #c9d1d9);
}
```

---

## Fase 8: Estado y Race Conditions

### 8.1 Race Conditions Identificadas
- `instances-panel.tsx` líneas 442-460: `handleStop/handleStart` llaman `fetchData()` sin await.
- `projects-panel.tsx` líneas 160-166: `handleSwitchTo` llama async `listWorkspaces` sin error handling.
- `deploy-panel.tsx` líneas 310-318: Múltiples llamadas async en secuencia sin coordinación.
- `admin-panel.tsx` línea 1269-1275: `loadTable` puede dejar UI inconsistente si falla la API.

### 8.2 Estado No Reseteado al Cambiar Contexto
- `addons-panel.tsx`: Al cambiar de proyecto, estado de addons anterior persiste.
- `deploy-panel.tsx`: `selectedWs` se resetea pero `selectedInstance` no.
- `workspaces-panel.tsx`: `browsePath` del file browser no se resetea al cambiar workspace.

### 8.3 Missing Loading/Error States
- `projects-panel.tsx`: Fetch de workspaces/instances sin spinner.
- `workspaces-panel.tsx`: No muestra error state si la API falla.
- `inbox-panel.tsx`: catch blocks tragan errores silenciosamente (líneas 59-64, 66-71).

---

## Fase 9: Responsive Design

### 9.1 Panels Sin Mobile Breakpoints
- `.proj-layout` — no mobile stack
- `.billing-overview-cards` — grid siempre 3 columnas
- `instances-panel.tsx` línea 250 — form 2 columnas sin breakpoint
- `workspaces-panel.tsx` línea 195 — sidebar fija 220px sin mobile

### 9.2 Admin Dashboard — 0 Responsive
- `globals.css` (admin) — 827 líneas sin un solo `@media` query
- Cards, grids, tablas — todo fijo para desktop

---

## Fase 10: Consistencia Admin ↔ Dashboard

### 10.1 Código Duplicado Entre Dashboards
| Elemento | Admin | Main | Solución |
|----------|-------|------|----------|
| Login form | `page.tsx` | `page.tsx` | Extraer `LoginForm` compartido |
| Logo SVG | 2 definiciones | 1 definición | Compartir componente |
| API client | 815 líneas | 1587 líneas | Crear `@nso/api-client` compartido |
| CSS base | 827 líneas | 2155 líneas | Extraer tokens/base compartidos |
| Format utils | inline en admin-panel | inline en panels | `@nso/format-utils` compartido |

### 10.2 Z86 Tab Huérfano
- `admin-panel.tsx` tiene `Z86Tab` implementado (línea 116).
- `admin-dashboard.tsx` navItems **no incluye** entrada para Z86.
- Código órfano — añadir a nav o eliminar.

---

## Fase 11: Seguridad

### 11.1 XSS Potencial
- `addons-panel.tsx` línea 379: `addon.description` renderizado directo.
- `admin-panel.tsx` línea 574-576: datos de usuario sin sanitizar.
- `deploy-panel.tsx` línea 301: log messages en `<span>` sin escape.
- `workspaces-panel.tsx` línea 345: contenido de archivo en `<pre>`.

### 11.2 Token Storage
- Tokens en `localStorage` — vulnerable a XSS.
- No hay refresh token mechanism.
- Admin token `sonfazt_token` en plain localStorage sin expiración.

### 11.3 Command Injection
- `admin-panel.tsx` línea 2667: Z86 terminal ejecuta comandos sin sanitización.
- `instances-panel.tsx` línea 677: `execOnInstance` envía comando raw.

### 11.4 Missing Confirmations
- `admin-panel.tsx` línea 2030: delete pool sin confirmación secundaria.
- `admin-panel.tsx` línea 1514: delete storage object con confirm() básico.

---

## Fase 12: Accesibilidad

### 12.1 ARIA Labels Faltantes
- `dashboard-layout.tsx` línea 458: botón de menú sin `aria-label`.
- `instances-panel.tsx` líneas 597-616: botones icon-only sin `title` ni `aria-label`.
- `addons-panel.tsx` línea 706-716: tabs sin `role="tablist"`.

### 12.2 Navegación por Teclado
- No hay focus trap en modales/viewers.
- Tabs no navegables con flechas.
- Terminal input no soporta Shift+Enter.

### 12.3 Contraste de Color
- `addons-panel.tsx` línea 393: `muted-foreground` sobre fondo claro puede fallar WCAG AA.
- Elementos con `opacity: 0.5` reducen contraste por debajo de AA.

---

## Orden de Ejecución

| # | Fase | Impacto | Esfuerzo | Archivos |
|---|------|---------|----------|----------|
| 1 | Bugs CSS (`--sidebar-bg`, colores duplicados) | Alto | Bajo | globals.css |
| 2 | Catch blocks silenciosos + 401 reload | Alto | Bajo | client.ts |
| 3 | Extraer utilidades compartidas (format, timeAgo) | Medio | Bajo | Nuevo format.ts + 6 panels |
| 4 | Active project restore | Medio | Bajo | dashboard-store.ts |
| 5 | Inline styles → CSS classes | Medio | Medio | 5 panels + globals.css |
| 6 | Terminal styles centralizados | Bajo | Bajo | 2 panels + globals.css |
| 7 | Race conditions + state reset | Alto | Medio | 4 panels |
| 8 | Partir admin-panel.tsx (2800 líneas) | Alto | Alto | admin/ |
| 9 | Partir billing/instances/addons panels | Medio | Alto | dashboard/ |
| 10 | Type safety (eliminar any) | Medio | Medio | types/ + panels |
| 11 | API client robustez (timeout, retry, split) | Alto | Medio | client.ts |
| 12 | Responsive breakpoints | Medio | Medio | globals.css × 2 |
| 13 | Z86 tab huérfano | Bajo | Bajo | admin-dashboard.tsx |
| 14 | Seguridad (XSS, sanitización) | Alto | Medio | Panels con render directo |
| 15 | Accesibilidad | Medio | Medio | Todos los panels |
