# PROGRESS — Gaming History Studio

Bitácora operativa del repositorio. Describe lo que existe y lo que se verificó,
no lo que se planea. Última actualización: **2026-11-23** (Fase 7 verificada en navegador).

## 1. Estado actual

| Fase | Alcance según SPEC.md | Estado |
| --- | --- | --- |
| 1 | Monorepo, Plugin Manager, manifiestos, base de datos y pantalla Extensiones con datos reales | **Completada y verificada** |
| 2 | Interfaz `EditorAdapter`, timeline unificado y `EditingRouter` | **Completada y verificada** |
| 3 | Integración FFmpeg completa y verificada con una operación real | **Completada y verificada** |
| 4 | Integración VectCutAPI/CapCut verificada | **Completada y verificada** (disco y confirmación visual en CapCut) |
| 5 | Integración DaVinci Resolve verificada | **Completada y verificada** (Free 21.0.4.5, puente in-app) |
| 6 | Integración Descript opcional | Pendiente (sin código) |
| 7 | Editor visual integrado con la timeline | **Completada y verificada** (Edge, FFmpeg, CapCut local y API viva de Resolve) |
| 8 | Sincronización con Google Drive | Pendiente (sin código) |

Notas de alcance:

- **Extensiones** (`/extensions`) y **Proyectos** (`/projects`, `/projects/[id]`) están activos;
  `/` redirige a `/extensions`. Dashboard, Trabajos globales y Auditoría no son pantallas
  implementadas. La lista de trabajos del proyecto vive dentro del editor.
- Existe el contrato `EditorAdapter`, el modelo unificado persistido de timeline y el
  `EditingRouter`; el adaptador FFmpeg ya es real, se autodescubre al arrancar y ejecuta
  importación, corte, unión, mezcla de audio, render y consulta de trabajos.
- La Fase 1 quedó commiteada como `06b4c68` (`Fase 1: Plugin Manager, manifiestos y pantalla
  Extensiones`); la Fase 2, como `49243a7` (`Fase 2: adaptadores, timeline y enrutador`). La
  Fase 3 se cierra con el commit de este cierre.
- La Fase 5 usa el puente local iniciado dentro de DaVinci Resolve. El scripting externo
   nativo sigue sin estar disponible en la edición Free probada.

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
- FFmpeg solo acepta rutas dentro de `GHS_WORKSPACE_DIR` (por defecto
  `backend/data/workspace`). Los renders y medios de prueba se crean ahí.

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

## Fase 2 — Contrato de adaptadores, timeline unificado y EditingRouter (2026-11-23)

- **Estado:** completada
- **Commit de cierre:** `49243a7`
- **Implementado:**
   - `backend/app/editing/adapter.py`: `EditorAdapter` abstracto con todos los métodos de la
    SPEC, `EditorOperation`, `AdapterCapabilities` y `execute_operation()`. El wrapper consulta
    `get_capabilities()` antes de invocar un método y rechaza operaciones no soportadas.
  - `backend/app/core/errors.py`: errores estructurados `PLUGIN_NOT_CONNECTED`,
    `ADAPTER_NOT_REGISTERED`, `INVALID_OPERATION` y `PROJECT_NOT_FOUND`; se conserva
    `PLUGIN_DISABLED` y `CAPABILITY_NOT_AVAILABLE` de la Fase 1.
  - `backend/app/editing/registry.py`: registro genérico `plugin_id -> factory/clase de
    EditorAdapter`, sin importaciones de adaptadores concretos desde el núcleo.
  - `backend/app/editing/timeline.py` y `persistence.py`: proyecto unificado Pydantic v2 con
    assets, escenas, pistas de vídeo/audio/subtítulos, clips, transiciones, efectos, metadatos,
    validación de referencias/duraciones/solapamientos y persistencia JSON en SQLite
    (`project_record`).
  - `backend/app/editing/converters.py`: contrato base Unified -> editor con
    `ConversionResult.unsupported` para informar elementos no exportables.
  - `backend/app/editing/router.py`: reglas de selección de SPEC, selección manual, coste,
    capacidades declaradas, instalación, conexión, estado habilitado y autorización explícita
    para plugins cloud. Las respuestas aclaran cuando no existe un adaptador ejecutable aún.
  - API: `GET/POST /api/projects`, `GET/PUT /api/projects/{id}`,
    `GET/PUT /api/projects/{id}/timeline`, `GET /api/router/decisions` y
    `POST /api/router/decide`.
  - Frontend: sección **Enrutador** en `/extensions`, con decisiones reales por operación,
    lista de descartes, recálculo y un control explícito de autorización cloud que solo afecta
    la decisión, nunca envía material.
  - `backend/tests/`: 34 pruebas para el contrato, validaciones/serialización/persistencia de
    timeline y reglas del router. `tests/dummy_adapter.py` es exclusivo de pruebas y no se
    importa ni registra en la app.
- **Probado realmente (comando → resultado):**
  - `backend\.venv\Scripts\python.exe -m pytest` → **34 passed**.
  - `backend\.venv\Scripts\python.exe -m compileall -q app` → exit 0.
  - `frontend\npm run lint` → sin errores ni warnings.
  - `frontend\npx tsc --noEmit` → exit 0.
  - `frontend\npm run build` → compilado; rutas `/`, `/_not-found` y `/extensions` generadas.
  - `GET /api/router/decisions` con el estado persistido real → `auto_assembly` eligió
    **FFmpeg**; `editable_draft`, `professional_edit` y `transcript_edit` no eligieron editor.
    VectCutAPI/CapCut y Descript se descartaron por dependencias ausentes; Resolve por no tener
    conexión verificada. FFmpeg se marca no ejecutable aún porque no existe adaptador concreto
    hasta Fase 3.
  - Operación HTTP real de proyectos → se creó un proyecto, se actualizó con asset/escena/pista,
    `GET /timeline` devolvió el clip persistido y una actualización con clips solapados recibió
    HTTP 422. El proyecto temporal se eliminó después de verificar.
  - `GET http://127.0.0.1:3000/extensions` → HTTP 200 y contenido de la sección Enrutador.
- **No probado / limitaciones:**
  - No se implementó ni ejecutó ningún adaptador de producción; FFmpeg queda expresamente para
    Fase 3. Por ello el router puede recomendar FFmpeg según estado/capacidades del manifiesto,
    pero informa `executable=false` y no intenta editar.
  - Las capacidades usadas por el router son las declaradas en los manifiestos hasta que exista
    un adaptador que pueda devolver capacidades verificadas por operación real.
  - No se contactó Descript ni se envió material a la nube. La autorización cloud se validó con
    pruebas unitarias sobre un plugin conectado simulado y con la regla real del endpoint.
  - No se hizo prueba visual interactiva en navegador de los controles nuevos; se verificó la
    carga HTTP de `/extensions`, TypeScript, lint y build.
- **Notas de entorno y estado:**
  - Plugins detectados/instalados/conectados: FFmpeg instalado y conectado; DaVinci Resolve
    instalado pero no conectado; VectCutAPI/CapCut y Descript no instalados por dependencias
    ausentes.
  - Puertos y procesos: backend Uvicorn en `127.0.0.1:8000`; frontend Next.js en
    `127.0.0.1:3000`.
  - Base de datos / auditoría: `backend/data/studio.db` contiene `plugin_state`, `audit_log` y
    ahora `project_record`; los cambios de timeline se guardan como JSON validado.
- **Próximo paso:**
  - Fase 3: implementar el adaptador FFmpeg y verificar una operación real de corte y unión,
    manteniendo el wrapper de capacidades como puerta obligatoria.

## Fase 3 — Integración FFmpeg verificada (2026-11-23)

- **Estado:** completada
- **Commit de cierre:** `2e6e3e2` (`fase 3: adaptador ffmpeg`)
- **Implementado:**
  - `backend/app/core/exec.py`: `run_command()` pasa `env=minimal_env()` al subproceso; los
    binarios ya no heredan credenciales del backend. Prueba `tests/test_exec.py` demuestra
    que una variable sensible no llega al hijo (`cmd.exe` responde `absent`).
  - `backend/app/editing/adapter.py`: `execute_operation()` ya no acepta `connected` del
    llamador; consulta el estado persistido (`PluginState.enabled` y `.connected`) y lanza
    `PLUGIN_NOT_CONNECTED` si la fila no existe o está deshabilitada. Se prueba contra
    `PluginState` real en base temporal (desconectado, deshabilitado y sin fila) y se verifica
    que pasar `connected=` lanza `TypeError`.
  - `backend/app/editing/adapters/ffmpeg.py`: `FFmpegAdapter` registrado con
    `@register_adapter("ffmpeg")`; `adapters/__init__.py` lo autodescubre y `main.py` lo
    importa en el arranque, sin que el núcleo lo conozca. Solo ejecuta `ffmpeg`/`ffprobe`
    mediante `core/exec.py` (lista de argumentos, sin shell, allowlist y timeout).
  - Validación de rutas: `workspace_path()` exige rutas dentro de `GHS_WORKSPACE_DIR`
    (`backend/data/workspace` por defecto), rechaza `..` y salidas fuera del workspace;
    sobrescribir exige `confirm_overwrite=true`.
  - `get_capabilities()` devuelve solo operaciones implementadas: `import_media`,
    `create_timeline`, `render_preview`, `render_final`, `export_project` y
    `get_job_status`. `verified` y las capacidades verificadas se leen de
    `plugin_state.config`, no están fijadas; se marcan tras operaciones reales.
  - `create_timeline` valida el proyecto persistido (assets/tracks/clips reales); el resto de
    métodos no implementados siguen lanzando `CapabilityNotAvailable`.
  - `FFmpegConverter`: traduce pistas de vídeo/audio a un grafo `filter_complex` (cortes con
    `-ss/-t`, normalización de tamaño/fps/audio, `concat`, mezcla con `amix`, ganancia con
    `volume` y posición con `adelay`). `ConversionResult.unsupported` informa transiciones,
    subtítulos, efectos, fundidos de audio, huecos entre clips y pistas de vídeo adicionales.
  - `backend/app/editing/jobs.py`: tabla `render_job` en SQLite con id, estado
    (`queued/running/done/failed`), progreso, log, error, timestamps y ruta de salida.
  - API: `POST /api/projects/{id}/media` (importación con ffprobe),
    `POST /api/projects/{id}/renders/{preview|final}` (job asíncrono y confirmación de
    sobrescritura), `GET /api/jobs`, `GET /api/jobs/{id}`.
  - Router: con adaptador registrado, `adapter_registered=true`, `executable=true` cuando la
    operación está implementada y `capability_source="adapter"`; las capacidades del router
    salen del adaptador y ya no de las declaraciones del manifiesto para FFmpeg.
  - `GET /api/plugins/{id}/capabilities` y `PluginView` incluyen capacidades declaradas,
    efectivas y verificadas. Frontend: panel de Extensiones muestra "declaradas vs.
    verificadas" con los datos reales; el panel del router ya no anuncia "Fase 3".
  - Pruebas nuevas: contrato real de FFmpeg (se omite con motivo si falta el binario),
    conversión Unified → FFmpeg, rechazo de rutas, persistencia de jobs, saneado del entorno
    del subproceso y gate de conexión contra `PluginState` persistido.
- **Probado realmente (comando → resultado):**
  - `python -m pytest` → **44 passed**.
  - `python -m pytest tests/test_exec.py tests/test_adapter_contract.py -o addopts="" -v` →
    14 passed. Con `GHS_TEST_SECRET` definida en el padre, `run_command("cmd.exe", ...)`
    devuelve `child_stdout=absent` (`parent_value=must-not-reach-child`).
  - Gate de conexión: 5 pruebas verdes (`desconectado`, `desconectado persistido`,
    `deshabilitado persistido`, `sin fila`, `connected=` rechazado con `TypeError`); en todas
    `adapter.calls == []` y no se consultan capacidades.
  - `python -m compileall -q app` → exit 0.
  - `npm run lint` → sin errores ni warnings.
  - `npm run build` → compilado; rutas `/`, `/_not-found` y `/extensions` generadas.
  - `npx tsc --noEmit` → exit 0 (tras `next build`, que genera `.next/types` con `LayoutProps`).
  - `ffmpeg -version` / `ffprobe -version` → 9.0.2 (Gyan build) presentes en PATH.
  - Se generaron dos clips reales de 2 s con `testsrc`/`testsrc2` + `sine`
    (`phase3-a.mp4`, `phase3-b.mp4`).
  - Importación por API con ffprobe → `durA=2.0`, `durB=2.0`.
  - Timeline real: corte de 0,8 s (desde 0,2 s) del clip A + corte de 1,2 s (desde 0,4 s) del
    clip B, contiguos → 2,0 s esperados.
  - Primer render real falló: FFmpeg exigía inputs de `concat` intercalados
    `[v0][a0][v1][a1]` y el conversor los agrupaba. Se registró como job `failed` y auditoría
    `render_final/error`; se corrigió el conversor y no se simuló el éxito.
  - Render final por API (job `d721163ca6964a65bd83a0275aace109`) → `done`, progreso 100.
  - `ffprobe` sobre `phase3-final.mp4` → existe, duración **2.000000 s**, streams `h264`
    (160×90) y `aac`.
  - `get_capabilities()` antes del render final exitoso → `media.inspect=verified`;
    `media.cut`, `media.concat`, `audio.mix`, `render.final=declared`; el resto
    `unsupported`. Después → las cinco capacidades `verified`.
  - Sobrescritura sin confirmación → 422 `INVALID_OPERATION` con mensaje explícito.
  - Ruta `../AGENTS.md` → 422 `INVALID_OPERATION` ("Las rutas con '..' no están permitidas").
  - `GET /api/router/decisions` → `auto_assembly`: FFmpeg, `capability_source="adapter"`,
    `adapter_registered=true`, `executable=true`.
  - Auditoría de FFmpeg: `import_media/ok`, `render_final/queued`, `running`, `ok` y el
    `error` real del primer intento.
  - Frontend dev levantado en `127.0.0.1:3000` con `NEXT_PUBLIC_API_URL=http://127.0.0.1:8011`;
    `GET /extensions` → 200. Backend de verificación en `127.0.0.1:8011` porque el puerto 8000
    estaba ocupado por otro proceso ajeno al proyecto.
- **No probado / limitaciones:**
  - No se implementan `create_project`, `add_track`, `add_clip`, `update_clip`,
    `remove_clip`, `add_audio`, `add_subtitles`, `add_effect`; siguen siendo
    `CapabilityNotAvailable`.
  - Transiciones, subtítulos, efectos, fundidos de audio, huecos sin clip y más de una pista
    de vídeo se reportan en `unsupported`, no se renderizan.
  - `render_preview` usa el mismo pipeline de recodificación que el final; no hay preview
    rápida ni `-preset` diferenciado.
  - El progreso es grueso (0 → 10 → 100); no se parsea el progreso incremental de FFmpeg.
  - Los jobs se ejecutan con `BackgroundTasks` en el mismo proceso: si el backend muere, un
    job `queued/running` queda huérfano y no hay recuperación automática.
  - No hay bloqueo por proyecto ni por ruta de salida: dos renders simultáneos podrían
    escribir el mismo archivo.
  - Siempre se recodifica a H.264/AAC; no hay stream copy ni selección de códecs/hardware.
  - Un único workspace configurable; no hay allowlist por proyecto ni por medio.
  - La UI se verificó con HTTP 200, lint, TypeScript y build; no se hizo prueba interactiva
    de navegador sobre las nuevas etiquetas declaradas/verificadas.
  - El estado verificado vive en `plugin_state.config`; borrar la base exige repetir las
    operaciones reales para volver a marcarlo.
- **Notas de entorno y estado:**
  - Plugins detectados/instalados/conectados: FFmpeg instalado y conectado con capacidades
    verificadas; DaVinci Resolve instalado y no conectado; VectCutAPI/CapCut y Descript sin
    dependencias.
  - Puertos y procesos: backend de verificación en `127.0.0.1:8011` (8000 ocupado por otro
    proyecto); frontend Next.js en `127.0.0.1:3000`. Logs del frontend en
    `%TEMP%\opencode\ghs-frontend.log`.
  - Base de datos / auditoría: `backend/data/studio.db` contiene `plugin_state`, `audit_log`,
    `project_record` y `render_job`. Medios y render de prueba en
    `backend/data/workspace/`.
- **Próximo paso:**
  - Fase 4: integración VectCutAPI/CapCut verificada, sin reutilizar el adaptador FFmpeg ni
    tocar el núcleo. Deuda técnica: progreso incremental real y recuperación de jobs
    interrumpidos.

## Fase 5 — Integración DaVinci Resolve (2026-11-23)

- **Estado:** completada y verificada en Free 21.0.4.5, mediante el puente in-app.
- **Commit de cierre:** `fase 5: adaptador davinci resolve`.
- **Implementado:** cliente TCP de loopback con peticiones HMAC; adaptador registrado para
  inspección del proyecto activo, creación de proyectos y timelines, importación, adición
  de pistas y clips, inicio de render y consulta del trabajo. El Plugin Manager comprueba
  el canal al conectar y diagnosticar. Extensiones muestra edición, versión y capacidades
  verificadas. «Edición profesional» exige conexión y evidencia de creación de timeline
  y colocación de clip. El conversor Unified → Resolve devuelve un plan e identifica
  elementos no exportables.
- **Probado realmente:** `health` → Free 21.0.4.5 y 15 operaciones; una operación no
  registrada → `operation_not_allowed`. La lista de nombres está en
  `E:\davinci-resolve-mcp\src\utils\resolve_bridge_ops.py:148–169`; el dispatcher solo
  registra esa lista (213–215) y rechaza otros nombres (225–232). `call` admite métodos
  públicos; las 15 operaciones son los nombres del protocolo, no los métodos de Resolve.
  `health.policy` → medios bajo `C:\Users\emil-`; salidas bajo `C:\Users\emil-\Movies`.
  El adaptador valida las rutas para sus métodos de importación y render vía `call`.
- **Endurecimiento del adaptador:** el cliente limita `call` a los 16 métodos que usa
  ResolveAdapter. Una llamada fuera de la lista devuelve `method_not_allowed` antes de
  cargar la configuración, firmar o abrir una conexión, y registra `bridge.call: denied`
  sin guardar datos de la petición. `python -m pytest` con `GHS_RESOLVE_LIVE=1` → **54 passed**,
  incluidos envío permitido, rechazo auditado, validación de rutas y render real.
- **Rango de colocación:** `ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=avg_frame_rate,nb_read_frames:format=duration -of default=nw=1 <archivo>`
  → fuente: 48 fotogramas a 24 fps (`2.000000 s`); primer render: 23 fotogramas
  (`0.958333 s`). El recorte previsto era de un segundo, pero `[0, 23)` excluía el
  fotograma 23. Al usar `[0, 24)`, la prueba real volvió a guardar un proyecto y renderizó
  24 fotogramas (`1.000000 s`) en `%USERPROFILE%\Movies\ghs-resolve-e6d146d3d8\result.mov`.
- **Pistas y credencial:** la prueba convierte `V1, A1, V2` a índices independientes
  por tipo. El clip en V2 sale con `trackIndex=2`; la lectura real de Resolve devuelve
  V1=0 clips, V2=1 clip y `GetDuration=24`. La misma prueba comparó la credencial sin
  imprimirla contra logs capturados, auditoría y payloads de API usados por la UI: ausente.
- **Comprobaciones:** `python -m pytest -rP` con `GHS_RESOLVE_LIVE=1` → **52 passed**;
  `python -m compileall -q app`, `npm run lint`, `npm run build` y `npx tsc --noEmit` → OK.
- **Cómo reproducir:** en Resolve, iniciar `Workspace → Scripts → resolve_bridge`. En
  `backend`, ejecutar `$env:GHS_RESOLVE_LIVE='1'; python -m pytest tests/test_resolve_live.py -rP`.
  Requiere FFmpeg/ffprobe y crea un proyecto y archivos de prueba. Desde Extensiones,
  instalar confirmando permisos, conectar y ejecutar el diagnóstico.
- **Limitaciones:** Extensiones muestra «Puente interno» y advierte que una actualización
  puede deshabilitarlo. El adaptador declara no disponible Free 21.1+; se verificó esa
  regla con pruebas unitarias de Free 21.1/22.0 y Studio 21.1, sin instalaciones reales
  de esas versiones. Studio sigue necesitando un puente funcional. El
  conversor produce un plan; no hay aún un envío automático de la timeline unificada
  desde la UI. El render final se probó con MOV/DNxHR; el modo de previsualización usa
  el mismo mecanismo y no se verificó por separado. La inserción de subtítulos, efectos
  y la exportación de proyectos no están implementadas.

### Diagnóstico histórico del scripting externo nativo

- **Estado en ese momento:** bloqueada antes de habilitar el puente in-app.
- **Commit del diagnóstico:** `96a3918`.
- **Implementado:**
  - Diagnóstico real previo, sin adaptador. No se escribió `resolve.py` ni se modificaron
    Plugin Manager, router, frontend o pruebas, porque el gate de la fase no se cumplió.
- **Probado realmente (comando → resultado):**
  - `Get-Process -Name Resolve` → Resolve abierto, PID 6392, inicio 23/11/2026 20:18:26;
    ventana `DaVinci Resolve - Crear proyecto 1`.
  - `(Get-Item Resolve.exe).VersionInfo` → `FileVersion=21.0.4.5`, `ProductVersion=21.0.4.5`,
    `ProductName=DaVinci Resolve`.
  - Registro de desinstalación → `DisplayName=DaVinci Resolve`, `DisplayVersion=21.0.40005`,
    sin "Studio".
  - Instalación → única entrada `Blackmagic Proxy Generator Lite.lnk` (edición Free), que
    apunta a `Resolve.exe -pg`; no existe la variante completa de Studio.
  - API oficial localizada en
    `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting`
    (`README.txt` actualizado 24/07/2026 y `Modules/DaVinciResolveScript.py`).
  - Con `RESOLVE_SCRIPT_API`, `RESOLVE_SCRIPT_LIB` y `PYTHONPATH` apuntando a esa instalación,
    Python 3.14.3 importa `DaVinciResolveScript`, pero `scriptapp("Resolve")` → `None`
    (sin objeto Resolve).
  - Python 3.12 sobre el mismo módulo termina con `0xC0000005` (`-1073741819`), descartado por
    incompatibilidad; no se usó para el diagnóstico.
  - El README empaquetado describe la API como "for DaVinci Resolve Studio" y la preferencia
    "External scripting using" como permiso configurable; en Free no entrega el objeto a un
    proceso externo. No se localizó clave de scripting en `config.dat` ni `config.user.xml`.
  - Resumen de la API según el README: desde fuera de Resolve se puede gobernar la app abierta
    (ProjectManager, proyectos, MediaPool, timelines, render, Fusion/Fairlight y ajustes) si
    hay Studio con scripting externo en Local/Network. En Free 21.0.4 no hay acceso externo;
    la API cubre un superconjunto común, pero el permiso y varias funciones son de Studio.
  - Conclusión: no hay canal externo vivo; no se creó adaptador ni se simuló ninguna
   operación.

## Fase 4 — VectCutAPI/CapCut (2026-11-23, hora local)

- **Estado:** completada; generación, lectura del artefacto real y revisión visual en CapCut verificadas.
- **Commit de cierre:** `fase 4: adaptador vectcutapi capcut` (el commit que incluye esta entrada).
- **Implementado:**
  - `editing/adapters/vectcut.py`: adaptador autodescubierto, conversor Unified → CapCut,
    validación de rutas, HTTP con timeout y auditoría, comprobación del contenido en disco
    y persistencia de capacidades tras la comprobación. Acepta MP4, MP3 básico y subtítulos
    SRT generados desde la timeline. Los elementos no traducidos se devuelven en `unsupported`.
  - `POST/GET /api/projects/{id}/drafts` para generar y consultar resultados. La copia a CapCut
    requiere `POST /api/projects/{id}/drafts/{draft_id}/deploy` con `{"confirm_copy":true}`.
    Usa la carpeta local corroborada por `root_meta_info.json` o `CAPCUT_DRAFTS_DIR` confirmada
    en Global Settings. No sobrescribe borradores ni modifica el catálogo de CapCut.
  - El manifiesto exige una comprobación HTTP real del adaptador. Extensiones usa su panel
    existente para mostrar declaradas vs. verificadas y las notas de borrador sin render y
    fragilidad del formato. «Borrador editable» solo selecciona CapCut conectado con las
    capacidades verificadas requeridas; la API permite la primera operación de comprobación.
- **Probado realmente (comando → resultado):**
  - `git -C E:\VectCutAPI rev-parse HEAD` → `5ae379b241d3d0a0f703e3095f3f0f96bd263ee4`.
    [`README.md` del upstream, líneas 16–24 y 47–60](https://github.com/sun-guannan/VectCutAPI/blob/5ae379b241d3d0a0f703e3095f3f0f96bd263ee4/README.md#L16-L60)
    distingue borradores locales de vista previa/render en nube; `MCP_Documentation_English.md:15–29` y
    `rest_client_test.http:14–33` describen el flujo de crear, insertar y guardar. Se usó HTTP
    directo con el contrato de `capcut_server.py`, no el proceso MCP ni servicios web.
  - `GET /` en `127.0.0.1:9000` → 404 de Werkzeug (no es un endpoint de salud).
    `POST /create_draft` con `{"width":320,"height":240}` → éxito,
    `dfd_cat_1795483657_59a0a447`. `POST /save_draft` con ese ID, `auto_deploy=false` y
    `auto_reload=false` → `E:\VectCutAPI\dfd_cat_1795483657_59a0a447`; `draft_info.json` en disco.
    `save_draft_impl.py:77–79` confirma el directorio por defecto y el override `draft_folder`.
    En la integración, la salida va a un subdirectorio nuevo dentro del workspace.
  - `ffmpeg -v error -n -f lavfi -i testsrc2=size=320x240:rate=24 -t 2 -c:v libx264 -pix_fmt yuv420p E:\GamingHistory\backend\data\workspace\phase4-diagnostic.mp4`
    → MP4 H.264 de 2 s. Proyecto `e43dbd1f6445464a9898b8f826bca8bd`: `POST .../drafts`
    con `{"width":320,"height":240}` → borrador `dfd_cat_1795484464_505eff12`, registrado
    y devuelto también por `GET .../drafts`. La lectura independiente de `draft_info.json` en
    `backend/data/workspace/vectcut-e93pnqv_/dfd_cat_1795484464_505eff12` confirmó el MP4 local,
    clip `[0, 1] s` desde `0,25 s` de la fuente y subtítulo **GHS Phase 4 - CapCut** de `0,20` a
    `0,85 s`. `draft_meta_info.json` contiene `cloud_draft_sync=false`.
  - `POST /api/plugins/vectcut-capcut/connect` → conectado por `GET /get_font_types`; el router
    devolvió `selected=null` antes de la prueba y `vectcut-capcut`, `executable=true` después.
  - `POST /api/projects/e43dbd1f6445464a9898b8f826bca8bd/drafts/dfd_cat_1795484464_505eff12/deploy`
    con `{"confirm_copy":true}` → copia autorizada y verificada en la carpeta local de CapCut.
  - Revisión manual en CapCut → el usuario confirmó que el borrador se ve.
  - En `backend/`: `$env:VECTCUT_ROOT='E:\VectCutAPI'; $env:GHS_VECTCUT_LIVE='1'; python -m pytest -o addopts= -q -rsP`
    → **60 passed, 1 skipped** (Resolve real no activado); la prueba viva de VectCut verificó
    vídeo, audio básico y subtítulo en disco. `python -m compileall -q app` → exit 0.
  - En `frontend/`: `npm run lint`, `npx tsc --noEmit` y
    `$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8012'; npm run build` → exit 0.
    `GET http://127.0.0.1:3001/extensions` → 200; `GET http://127.0.0.1:8012/api/health`
    con ese origen → 200, CORS correcto, 4 manifiestos y 0 errores.
- **No probado / limitaciones:**
  - Se confirmó la visualización; no se verificó por separado editar y volver a guardar el
    subtítulo. El formato `capcut_legacy` es privado y el editor puede dejar de abrirlo después
    de una actualización. No hay render final por VectCutAPI,
    efectos, transiciones ni materiales Pro en este flujo.
  - No se usan enlaces de vista previa, descarga remota ni subida. El cliente limita HTTP a
    loopback sin proxy ni redirecciones, admite `VECTCUT_ENDPOINT` para otro puerto local y
    comprueba la configuración del checkout confiable indicado por `VECTCUT_ROOT`.
    No había `config.json` y el upstream observado declara `IS_UPLOAD_DRAFT=False`
    en `settings/local.py:24–28`. El API no certifica la configuración de su proceso:
    `VECTCUT_ROOT` debe corresponder al servicio arrancado, y los cambios de configuración
    requieren reiniciarlo. El flujo local probado no utiliza la nube de CapCut Desktop.
- **Notas de entorno y estado:**
  - CapCut internacional gratuito instalado: `C:\Users\emil-\AppData\Local\CapCut\Apps\8.5.0.3590\CapCut.exe`
    (`ProductVersion=8.5.0.800f1aa5`). `root_meta_info.json` confirma como `root_path`
    `C:\Users\emil-\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft`.
  - VectCutAPI/FFmpeg conectados; VectCutAPI en `127.0.0.1:9000` vía `venv-capcut`, backend
    Uvicorn en `127.0.0.1:8012` y frontend Next (`npm run start`) en `127.0.0.1:3001`.
  - `backend/data/studio.db`: `draft_result`, capacidades en `plugin_state.config` y llamadas
    HTTP auditadas en `audit_log`. El original permanece en el workspace; la copia autorizada
    está en `C:\Users\emil-\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\dfd_cat_1795484464_505eff12`.
- **Próximo paso:** repetir la prueba de apertura si se actualiza CapCut o VectCutAPI.

## Fase 7 — Editor visual integrado (2026-11-23, hora local)

- **Estado:** completada para el alcance mínimo y verificada con navegador real.
- **Commit de cierre:** `fase 7: editor visual` (commit que incluye esta entrada).
- **Implementado:**
  - `/projects`: listado, creación y apertura de proyectos reales. `/projects/[id]`: recursos locales,
    tres tipos de pista, regla y zoom, selección, movimiento y recortes con ratón o teclado,
    edición de subtítulos, borrado, guardado explícito y 50 pasos de historial local.
  - `POST /api/projects/{id}/timeline/validate` valida propuestas sin persistir; `PUT .../timeline`
    mantiene la timeline unificada como fuente de verdad. Los cambios rechazados no entran en el historial.
  - `GET /api/projects/{id}/exports/{target}/preflight` combina router, capacidades verificadas,
    estado vivo cuando corresponde y salida `unsupported` del conversor. Se revisa antes de confirmar;
    se comprueba la revisión guardada en el envío. FFmpeg y CapCut usan sus endpoints existentes;
    `POST /api/projects/{id}/exports/resolve` crea y guarda un proyecto local mediante el adaptador.
  - Trabajos del proyecto con polling, progreso, estados reales, log y descarga mediante
    `GET /api/jobs/{id}/result` para resultados completos dentro del workspace.
- **Probado realmente (comando → resultado):**
  - En `backend`, con `GHS_RESOLVE_LIVE=1`, `GHS_VECTCUT_LIVE=1` y `VECTCUT_ROOT=E:\VectCutAPI`:
    `python -m pytest -o addopts= -q -rs` → **64 pasaron**, incluida la prueba de Resolve Free 21.0.4.5
    en una base de pruebas: preflight disponible, POST de envío 201 y lectura real de V2 con un clip de
    24 fotogramas. `python -m compileall -q app` → OK.
  - En `frontend`: `npm run lint`, `npx tsc --noEmit` y `npm run build` con
    `NEXT_PUBLIC_API_URL=http://127.0.0.1:8017` → OK; `npm test` → **3 pasaron** (runner de Node).
  - Desde la raíz, con Edge instalado y Playwright para Python:
    `python scripts/verify_phase7.py --web http://127.0.0.1:3017 --api http://127.0.0.1:8017 --workspace E:\GamingHistory\backend\data\workspace --evidence "$env:TEMP\opencode\ghs-phase7-evidence-final" --send-capcut`
    → Edge 158 headless: creó y reabrió `c100228451674b1a850aaf4660062f3c`, rechazó la ruta fuera del
    workspace, importó dos MP4 de 2 s generados por FFmpeg y verificó recorte inicial por teclado,
    recorte final y movimiento con ratón, deshacer/rehacer, texto de subtítulo y persistencia tras recarga.
    El solapamiento devolvió HTTP 422; la UI mostró el motivo y conservó el clip en su sitio.
  - El preflight mostró la omisión del subtítulo antes de confirmar el render. El trabajo terminó
    en `done`, se descargó por la UI y `ffprobe -v error -show_entries format=duration:stream=codec_name -of json <render-ffmpeg.mp4>`
    devolvió **3.000000 s · H.264 / AAC**. CapCut estaba disponible y devolvió HTTP 201 para el borrador
    local `dfd_cat_1795486590_e70f9e41`. En la base de la sesión del navegador el plugin Resolve no
    estaba instalado en Studio; el botón se mostró deshabilitado con ese motivo.
  - Evidencia: `%TEMP%\opencode\ghs-phase7-evidence-final\`, capturas `01-timeline-persistida.png`,
    `02-solapamiento-rechazado.png`, `03-preflight-ffmpeg.png`, `04-render-completado.png`,
    `05-preflight-capcut.png`, `06-resultado-capcut.png`, `07-disponibilidad.png`, `08-timeline-movil.png`
    y `09-listado-proyectos.png`. El MP4 descargado está en la misma carpeta.
- **No probado / limitaciones:**
  - En esta fase no se abrió en CapCut Desktop el nuevo borrador. Se verificó su generación en disco;
    no se modificó el estado ni la confirmación histórica de Fase 4.
  - La confirmación de Resolve con el plugin activo se verificó vía API y puente en vivo, no con el
    clic en Edge. El flujo exige rutas compatibles tanto con `GHS_WORKSPACE_DIR` como con el puente.
  - En Edge se verificó el trabajo completado y su descarga, no se indujo un render fallido ni se
    hizo una auditoría formal de accesibilidad. El historial no sobrevive a la recarga.
- **Notas de entorno y estado:**
  - FFmpeg y VectCutAPI conectados; Resolve verificado en base de pruebas separada; sin envío a la nube.
  - Next `127.0.0.1:3017`, Uvicorn `127.0.0.1:8017`, VectCutAPI `127.0.0.1:9000`. Logs:
    `%TEMP%\opencode\ghs-phase7-next.log` y `%TEMP%\opencode\ghs-phase7-uvicorn.log`.
  - SQLite `backend/data/studio.db` conserva los proyectos, trabajos, borradores y auditoría. Los
    medios y resultados originales se guardaron en `backend/data/workspace`.
- **Próximo paso:** repetir el envío a Resolve desde la UI cuando esté habilitado en la base habitual,
  con medios en una ruta admitida por ambas aplicaciones.
