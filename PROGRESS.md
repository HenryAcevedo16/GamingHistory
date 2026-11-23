# PROGRESS — Gaming History Studio

Bitácora operativa del repositorio. Describe lo que existe y lo que se verificó,
no lo que se planea. Última actualización: **2026-11-23** (cierre de Fase 1).

## 1. Estado actual

| Fase | Alcance según SPEC.md | Estado |
| --- | --- | --- |
| 1 | Monorepo, Plugin Manager, manifiestos, base de datos y pantalla Extensiones con datos reales | **Completada y verificada** |
| 2 | Interfaz `EditorAdapter`, timeline unificado y `EditingRouter` | Pendiente (sin código) |
| 3 | Integración FFmpeg completa y verificada con una operación real | Pendiente (sin código) |
| 4 | Integración VectCutAPI/CapCut verificada | Pendiente (sin código) |
| 5 | Integración DaVinci Resolve verificada | Pendiente (sin código) |
| 6 | Integración Descript opcional | Pendiente (sin código) |
| 7 | Editor visual integrado con la timeline | Pendiente (sin código) |
| 8 | Sincronización con Google Drive | Pendiente (sin código) |

Notas de alcance:

- Solo existe la pantalla **Extensiones** (`/extensions`); `/` redirige con 307 a
  `/extensions`.
- En la barra lateral, Dashboard, Proyectos, Trabajos y Auditoría son elementos
  deshabilitados con etiquetas "Fase 2", "Fase 2", "Fase 4" y "Fase 8". No son pantallas
  implementadas.
- No existe todavía `EditorAdapter`, modelo de timeline, `EditingRouter`, adaptadores de
  edición ni ejecución real de herramientas de terceros.
- El repositorio git no tiene commits (`master` sin historial) y todo el proyecto está sin
  seguimiento al cierre. **No hay commit de cierre de Fase 1.**

## 2. Cómo ejecutar (Windows / PowerShell)

Requisitos observados en esta máquina: Python 3.13.3, Node.js v22.16.0, npm 11.6.2.

### Backend

```powershell
cd C:\Users\168056\Desktop\gaming-history-studio\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- El proceso **debe** lanzarse desde `backend/`: si se lanza desde la raíz, uvicorn falla
  con `ModuleNotFoundError: No module named 'app'` (comprobado).
- API: http://127.0.0.1:8000 · Swagger: http://127.0.0.1:8000/docs
- Configuración con variables `GHS_*`; ver `backend/.env.example`.
- La base SQLite se crea automáticamente en `backend/data/studio.db`.

### Frontend

```powershell
cd C:\Users\168056\Desktop\gaming-history-studio\frontend
npm install
npm run dev
```

- Abrir http://localhost:3000 (redirige a `/extensions`).
- URL del backend: `NEXT_PUBLIC_API_URL`; por defecto `http://127.0.0.1:8000`.
- `next.config.ts` incluye `allowedDevOrigins: ["localhost", "127.0.0.1"]` para que el
  modo dev funcione también entrando por `127.0.0.1:3000`.

### Logs

Ejecución en primer plano: los logs van a la consola; no hay archivo por defecto.

Al cierre de esta sesión ambos servidores quedaron levantados con salida redirigida:

- Backend: `%TEMP%\opencode\ghs-backend.out.log` (stdout y stderr juntos).
- Frontend: `%TEMP%\opencode\ghs-frontend.log`.
- Puertos al cierre: 8000 (uvicorn) y 3000 (Next.js).

Comandos usados para reproducir esos logs:

```powershell
# Backend (WorkingDirectory = ...\backend)
Start-Process cmd.exe -ArgumentList '/c','.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > "%TEMP%\opencode\ghs-backend.out.log" 2>&1' -WorkingDirectory 'C:\Users\168056\Desktop\gaming-history-studio\backend' -WindowStyle Hidden

# Frontend (WorkingDirectory = ...\frontend)
Start-Process cmd.exe -ArgumentList '/c','npm run dev > "%TEMP%\opencode\ghs-frontend.log" 2>&1' -WorkingDirectory 'C:\Users\168056\Desktop\gaming-history-studio\frontend' -WindowStyle Hidden
```

El estado de ciclo de vida vive en `backend/data/studio.db` (tablas `plugin_state` y
`audit_log`). Los manifiestos **no** se copian a la base: siguen en disco y se releen en
cada petición.

## 3. Fase 1

### 3.1 Implementado

**Backend (`backend/app/`)**

- `core/config.py`: settings `GHS_*` con `pydantic-settings`; rutas por defecto de
  plugins y SQLite; CORS para `localhost:3000` y `127.0.0.1:3000`.
- `core/db.py`: engine SQLModel/SQLite (`check_same_thread=False`, `pool_pre_ping`),
  `init_db()` y sesión por request.
- `core/errors.py`: errores estructurados `StudioError` y subtipos (`PluginNotFound`,
  `PluginDisabled`, `PluginNotInstalled`, `PermissionsNotAcknowledged`,
  `DependencyUnavailable`, `InvalidManifest`, `CapabilityNotAvailable`).
- `core/exec.py`: ejecución de binarios con lista de argumentos, `shell=False`,
  allowlist por manifiesto, timeout y resolución por PATH. Rechaza rutas en el nombre del
  binario. Nota: define `minimal_env()`, pero `run_command` **todavía no lo aplica**, así
  que los procesos hijos heredan el entorno del backend.
- `models/plugin.py`: `PluginState` (estado persistido, diagnóstico, timestamps).
- `models/audit.py`: `AuditLog` append-only.
- `plugins/manifest.py`: esquema Pydantic estricto (`extra="forbid"`) del manifiesto,
  incluidos `requirements`, `permissions`, `tools`, `capabilities`, `known_costs` y
  `diagnostics`; tipos `binary|file|env|tcp|http|command`.
- `plugins/registry.py`: escaneo de `plugins/*/manifest.json`, validación, detección de
  ids duplicados y reporte de errores sin romper el catálogo.
- `plugins/diagnostics.py`: sondas reales (`binary`, `file`, `env`, `tcp`, `http`,
  `command`), expansión de `${VAR|default}` y `%VAR%`, versiones extraídas de la salida,
  resumen pass/fail/warn/skip. `command` ejecuta el binario indicado con args (no usa
  shell).
- `plugins/manager.py`: ciclo de vida completo; instalar exige confirmación de los
  permisos que la requieren y un diagnóstico real; conectar exige al menos un check
  **no opcional** de tipo `binary|command|tcp|http` en estado `pass`; desconectar,
  habilitar/deshabilitar, diagnóstico, verificación de requisitos y auditoría.
- `plugins/schemas.py`: contratos de respuesta (`PluginView`, `PluginListResponse`,
  `DiagnosticResponse`, `RequirementReport`, `ActionResponse`, etc.).
- `api/routes/health.py` y `api/routes/plugins.py`: endpoints REST.
- `main.py`: app FastAPI, CORS, `init_db()` en lifespan, handler JSON de `StudioError`.

Endpoints existentes (prefijo `/api`):

| Método | Ruta |
| --- | --- |
| GET | `/health` |
| GET | `/plugins` |
| GET | `/plugins/{id}` |
| POST | `/plugins/{id}/install` |
| POST | `/plugins/{id}/connect` |
| POST | `/plugins/{id}/disconnect` |
| POST | `/plugins/{id}/enable` |
| POST | `/plugins/{id}/disable` |
| GET | `/plugins/{id}/tools` |
| GET | `/plugins/{id}/capabilities` |
| POST | `/plugins/{id}/verify-requirements` |
| POST | `/plugins/{id}/diagnose` |
| GET | `/plugins/{id}/audit?limit=50` |

**Manifiestos (`plugins/`)**

| Plugin | Conexión | Herramientas | Capacidades | Checks de diagnóstico |
| --- | --- | --- | --- | --- |
| `ffmpeg` | `local-binary` | 10 | 10 | `ffmpeg -version`, `ffprobe -version` |
| `vectcut-capcut` | `mcp-http` | 8 | 8 | env opcional `VECTCUT_ENDPOINT`, HTTP a `${VECTCUT_ENDPOINT|http://127.0.0.1:9000}`, archivos de CapCut (opcional) |
| `davinci-resolve` | `mcp-stdio` | 9 | 7 | archivo `Resolve.exe`, env opcionales de scripting, binario opcional `uvx --version` |
| `descript` | `cloud-api` | 7 | 7 | env obligatorio `DESCRIPT_API_TOKEN`, env opcional `DESCRIPT_MCP_ENDPOINT` |

**Frontend (`frontend/`)**

- Next.js 16.4.6 (App Router, Turbopack), React 19.3, Tailwind 4.3, shadcn/ui con preset
  **base-nova** (componentes sobre `@base-ui/react`, no Radix), Framer Motion, lucide-react.
- Layout: sidebar fija, versión móvil con `Sheet`, barra superior móvil y estado real del
  backend con polling cada 30 s (`BackendStatus`).
- Pantalla `/extensions`:
  - tarjetas de stats (catálogo, instalados, conectados, atención),
  - pestañas Disponibles / Instalados / Conectados con contadores,
  - búsqueda por nombre/descripción/categoría/id,
  - skeletons, estados vacíos, banner de errores de manifiesto, banner de feedback,
  - tarjetas de plugin con icono generado (iniciales/acento del manifiesto), versión,
    estado, coste, herramientas/capacidades, diagnóstico guardado y acciones
    instalar/conectar/desconectar,
  - panel lateral de detalle con requisitos y evidencia, herramientas, capacidades
    declaradas, permisos, diagnóstico, datos de conexión y último error,
  - diálogo de permisos previo a instalar, con confirmación explícita.
- Cliente API tipado (`src/lib/api.ts`, `src/lib/types.ts`) con errores `ApiError` que
  conservan `code`, `status` y `details`.
- Tema oscuro con fuentes `next/font` (Inter, Sora, JetBrains Mono), utilidades de vidrio
  y tokens OKLCH en `globals.css`.

**Operación**

- `README.md` raíz, `backend/requirements.txt`, `backend/.env.example`, `.gitignore`.

### 3.2 Probado realmente (2026-11-23)

Comandos y resultados:

- `npm run lint` → sin errores ni warnings.
- `npx tsc --noEmit` → exit 0.
- `npm run build` → compilado; rutas `/`, `/_not-found` y `/extensions` generadas.
- `GET /api/health` → 200; `status=ok`, 4 plugins, 0 errores de manifiesto.
- `GET /api/plugins` con `Origin: http://localhost:3000` → 200 y cabecera
  `Access-Control-Allow-Origin: http://localhost:3000`.
- `GET /` en el frontend → 307 con `Location: /extensions`.
- Captura headless de Edge sobre `/extensions`: la página cargó el catálogo real (stats 4
  detectados, 2 instalados, 1 conectado; tarjetas de CapCut/VectCutAPI y Descript en
  Disponibles). La captura por `127.0.0.1` falló antes de añadir `allowedDevOrigins`
  (los recursos dev de Next estaban bloqueados); tras el cambio, la carga por
  `127.0.0.1` también funcionó.
- Diagnósticos ejecutados por HTTP para los cuatro plugins:
  - `ffmpeg`: `ok=true`, 2 pasan. `ffmpeg 9.0.2-full_build` y `ffprobe 9.0.2` desde
    WinGet.
  - `vectcut-capcut`: `ok=false`; HTTP a `127.0.0.1:9000` rechazado
    (`WinError 10061`), variable `VECTCUT_ENDPOINT` no definida, rutas de CapCut no
    encontradas (aviso opcional).
  - `davinci-resolve`: `ok=true`; `Resolve.exe` encontrado en
    `C:\Program Files\Blackmagic Design\DaVinci Resolve\`, `uvx 0.13.7`, variables
    `RESOLVE_SCRIPT_API`/`RESOLVE_SCRIPT_LIB` no definidas (omitidas por opcionales).
  - `descript`: `ok=false`; `DESCRIPT_API_TOKEN` no definida.
- Flujos HTTP verificados (evidencia también en `audit_log`):
  - Instalar `vectcut-capcut` sin `confirm_permissions` → 409
    `PERMISSIONS_NOT_ACKNOWLEDGED`.
  - Instalar `vectcut-capcut` con permisos → 409 `DEPENDENCY_UNAVAILABLE` (endpoint
    caído); auditoría con `install/denied` e `install/error`.
  - Instalar `ffmpeg` → 200 y auditoría `install/ok`; conectar → 200 y
    `connect/ok`.
  - Instalar `davinci-resolve` → 200 (`install/ok`); conectar → 409 con el mensaje de que
    solo se confirmaron archivos/variables, no un canal vivo
    (`connect/error`). El único check de canal (`uvx`) está declarado como opcional, por
    lo que no habilita la conexión.

Estado persistido al cierre (consulta directa a SQLite):

| Plugin | `install_status` | `enabled` | `connected` | Último diagnóstico |
| --- | --- | --- | --- | --- |
| `ffmpeg` | `installed` | true | **true** | ok |
| `davinci-resolve` | `installed` | true | false | ok |
| `vectcut-capcut` | `not_installed` | true | false | con fallos |
| `descript` | `not_installed` | true | false | con fallos |

Acciones registradas en auditoría: instalaciones de ffmpeg y Resolve, conexión de ffmpeg,
rechazo de conexión de Resolve, intento denegado y fallido de VectCutAPI, y diagnósticos
de los cuatro plugins.

### 3.3 Limitaciones de la Fase 1

- No hay adaptadores `EditorAdapter`, timeline unificado, `EditingRouter` ni operaciones
  de edición (Fase 2+).
- No se ejecuta ninguna herramienta de plugin: `tools` y `capabilities` son declaraciones
  del manifiesto. El estado `declared` no se convierte en `verified`.
- No existe el botón "Probar plugin" de la SPEC; hay "Ejecutar diagnóstico" y "Verificar
  dependencias".
- No hay configuración/almacenamiento de credenciales en la UI; solo se comprueba la
  presencia de variables de entorno (sin exponer valores).
- No hay pruebas automatizadas (unitarias/integración E2E). La verificación fue manual y
  por HTTP.
- Deuda de seguridad: `run_command` no pasa `env=minimal_env()`, por lo que ffmpeg/uvx
  heredan todas las variables del backend (incluidas credenciales presentes en el
  entorno). No se comprobó explotación; es una corrección pendiente.
- No se probaron clics reales en el diálogo de permisos, panel lateral o pestañas; la UI se
  verificó visualmente en la pestaña Disponibles con datos reales.
- Nunca se contactó con servicios en la nube (Descript) ni se envió material.
- VectCutAPI no estaba disponible; CapCut no está instalado. Resolve está instalado pero
  sin canal de ejecución vivo. Descript no tiene token.
- Las tarjetas del frontend muestran "Instalados" como `total − disponibles` (incluye
  conectados); el `counts.installed` del backend solo cuenta el estado exacto `installed`.

## 4. Decisiones técnicas y por qué

1. **Un plugin = una carpeta con `manifest.json`; el núcleo no se toca.** El registro
   descubre y valida manifiestos; añadir un plugin no requiere cambios en backend ni
   frontend. Los manifiestos se releen en cada petición, así que un cambio se refleja sin
   reiniciar.
2. **El manifiesto es la única fuente de verdad de lo declarado.** Requisitos,
   permisos, herramientas, capacidades, costes y diagnósticos se derivan de él. La UI no
   contiene datos de plugins hardcodeados.
3. **Esquema Pydantic estricto (`extra="forbid"`).** Un campo mal escrito o un id
   inválido se reporta como error de manifiesto en `/api/plugins` y `/api/health` en lugar
   de ignorarse silenciosamente.
4. **Diagnósticos genéricos dirigidos por datos.** `binary`, `file`, `env`, `tcp`, `http`
   y `command` cubren binarios locales, instalaciones, variables, endpoints MCP y APIs sin
   escribir código por plugin. La expansión `${VAR|default}` permite endpoints
   configurables.
5. **Instalar y conectar son cosas distintas.** `install` exige confirmar los permisos
   que lo requieren y ejecutar el diagnóstico real; `connect` vuelve a diagnosticar y exige
   un canal vivo **no opcional**. Así "instalado" no implica "funciona", y un archivo
   encontrado o una variable definida no bastan para declarar una conexión.
6. **Los checks opcionales no bloquean.** `DiagnosticReport.ok` solo exige que pasen los
   checks obligatorios; los opcionales pueden quedar en `skip`/`warn`. Por eso Resolve
   puede instalar sin variables de scripting, pero no conectar sin un canal vivo.
7. **SQLite/SQLModel solo para estado de ciclo de vida y auditoría.** Los manifiestos
   permanecen en disco; la base guarda `plugin_state` y `audit_log`. Es suficiente para
   una app local de un usuario y evita duplicar la fuente de verdad.
8. **Ejecución de comandos sin shell.** Listas de argumentos, `shell=False`, allowlist
   derivada del manifiesto, rechazo de rutas en el nombre del binario y timeout. Reduce la
   superficie de inyección. Queda pendiente aplicar `minimal_env()` al `subprocess`; hoy
   el hijo hereda el entorno completo del backend (ver limitaciones).
9. **Secretos: solo presencia, nunca valor.** Los checks `env` reportan "definida/no
   definida" sin imprimir el valor, y no hay almacenamiento de credenciales en Fase 1.
10. **Errores estructurados.** `StudioError` produce `{"error": {code, message, details}}`
    con códigos estables (`PERMISSIONS_NOT_ACKNOWLEDGED`, `DEPENDENCY_UNAVAILABLE`, etc.)
    que el frontend usa para mostrar evidencia de los checks fallidos.
11. **Un solo `display_status` derivado.** Prioridad: `error` → `disabled` → `connected`
    → `installed` → `available`. Evita estados contradictorios entre campos.
12. **Frontend guiado por API.** El cliente hace `fetch` con `cache: "no-store"`; las
    acciones refrescan el catálogo. Así la UI refleja el estado real y los errores del
    backend en cada operación.
13. **shadcn/base-nova (Base UI).** Fue el preset instalado; se asumió su API (`render`
    en `Button`, `onCheckedChange` en `Switch`) y se validó con TypeScript y build. Los
    anchos del panel y del diálogo se ajustaron con clases propias en `globals.css`.
14. **Tema oscuro y accesibilidad base.** Tokens OKLCH, foco visible, `aria-*` en
    pestañas y controles, y primitivas de Base UI. No se hizo una auditoría formal de
    accesibilidad y el modo claro de la SPEC no está implementado.
15. **Redirección y orígenes de desarrollo.** `/` redirige a `/extensions` para que la
    única pantalla real sea la entrada. `allowedDevOrigins` permite usar
    `localhost` y `127.0.0.1` en dev sin bloquear recursos de Next.

## 5. Plantilla para la siguiente fase

Copiar esta sección al final del documento y completarla al cerrar cada fase. No borrar
las fases anteriores.

```markdown
## Fase N — <nombre de la fase> (<fecha>)

- **Estado:** completada / parcial / bloqueada
- **Commit de cierre:** <hash> (o "sin commit")
- **Implementado:**
  - <módulos, endpoints, pantallas, manifiestos>
- **Probado realmente (comando → resultado):**
  - <comando exacto> → <resultado observado>
  - <operación real verificada con evidencia>
- **No probado / limitaciones:**
  - <lo que no se pudo verificar y por qué>
- **Notas de entorno y estado:**
  - Plugins detectados/instalados/conectados:
  - Puertos y procesos:
  - Base de datos / auditoría:
- **Próximo paso:**
  - <siguiente fase o deuda técnica concreta>
```
