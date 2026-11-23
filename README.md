# Gaming History Studio

Centro de control para coordinar editores de video externos (FFmpeg, CapCut/VectCutAPI,
DaVinci Resolve, Descript) mediante plugins y servidores MCP.

Esta entrega cubre la **Fase 1**: Plugin Manager + backend FastAPI con diagnósticos reales
y pantalla de Extensiones en Next.js. No incluye todavía adaptadores `EditorAdapter`,
timeline unificada ni operaciones de edición.

## Estructura

```
backend/            FastAPI + SQLModel (SQLite)
  app/api/routes/   endpoints REST
  app/plugins/      manifiestos, registro, diagnósticos y PluginManager
  data/studio.db    estado persistido (se crea solo)
plugins/            un directorio por plugin con manifest.json
frontend/           Next.js App Router + TypeScript + Tailwind + shadcn/ui
```

## Requisitos

- Python 3.11+
- Node.js 20+
- Herramientas externas opcionales según el plugin (FFmpeg, DaVinci Resolve, etc.).
  Si faltan, la UI lo reporta como fallo real; no se simula éxito.

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API: http://127.0.0.1:8000
- Documentación interactiva: http://127.0.0.1:8000/docs
- Configuración por variables `GHS_*` (ver `backend/.env.example`).
- SQLite se crea en `backend/data/studio.db`.

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Abrir http://localhost:3000 (redirige a `/extensions`).

Variables opcionales:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## Endpoints principales

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/api/health` | Estado del backend, plugins detectados y errores de manifiesto |
| GET | `/api/plugins` | Catálogo con estado y conteos |
| GET | `/api/plugins/{id}` | Detalle de un plugin |
| POST | `/api/plugins/{id}/install` | Instala tras verificar dependencias reales |
| POST | `/api/plugins/{id}/connect` | Conecta si existe un canal de ejecución vivo |
| POST | `/api/plugins/{id}/disconnect` | Desconecta |
| POST | `/api/plugins/{id}/enable` \| `/disable` | Habilita o deshabilita |
| POST | `/api/plugins/{id}/verify-requirements` | Verifica requisitos del manifiesto |
| POST | `/api/plugins/{id}/diagnose` | Ejecuta diagnósticos y devuelve evidencia |
| GET | `/api/plugins/{id}/tools` | Herramientas declaradas |
| GET | `/api/plugins/{id}/capabilities` | Capacidades declaradas |
| GET | `/api/plugins/{id}/audit` | Auditoría de acciones |

## Manifiestos de plugins

Cada plugin vive en `plugins/<id>/manifest.json`. Los campos obligatorios y los tipos de
diagnóstico están definidos en `backend/app/plugins/manifest.py`. Añadir un plugin no
requiere tocar el núcleo: basta con crear el directorio y su manifiesto.

Diagnósticos soportados (todos reales): `binary`, `software`, `file`, `env`, `tcp`, `http`,
`command`, `python`.

## Reglas del proyecto

- Cero integraciones simuladas: si algo no está soportado se lanza
  `CapabilityNotAvailable` o se reporta el fallo real.
- `install` exige confirmación de permisos y verifica dependencias antes de marcar el
  plugin como instalado.
- `connect` exige un canal de ejecución vivo (binario, comando, TCP o HTTP correcto).
- Los comandos se ejecutan como listas de argumentos, con allowlist de binarios y timeout.
- Toda acción queda registrada en la tabla de auditoría.

## Estado de esta fase y limitaciones

Probado con datos reales en esta máquina:

- FFmpeg detectado, instalado y conectado (comprobación real de `ffmpeg -version`).
- DaVinci Resolve detectado en disco e instalado; la conexión se rechaza si no hay canal
  vivo (por ejemplo, Resolve cerrado o bridge no disponible).
- CapCut/VectCutAPI y Descript reportan dependencias no disponibles sin simular éxito.
- Las capacidades y herramientas se muestran tal como las declara cada manifiesto; la
  ejecución real de herramientas llega con los adaptadores de fases posteriores.
- Todavía no existen adaptadores `EditorAdapter`, timeline unificada ni render.
