# Gaming History Studio

Centro de control que coordina editores de video externos (FFmpeg, CapCut/VectCutAPI, DaVinci Resolve, Descript) mediante plugins y servidores MCP.

## Stack
- Frontend: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Framer Motion
- Backend: Python 3.11+ con FastAPI, Pydantic v2, SQLModel + SQLite
- Monorepo: /frontend, /backend, /plugins

## Especificación completa
El detalle (arquitectura, adaptadores, timeline, pantallas y fases) está en SPEC.md. Leer SPEC.md y la sección de la fase en curso antes de empezar cada fase.

## Reglas no negociables
- Cero integraciones simuladas. Si algo no está soportado, lanzar CapabilityNotAvailable. Nunca simular éxito.
- Consultar get_capabilities() antes de cualquier operación.
- No construir un editor de video completo. Usar herramientas existentes.
- No enviar material a la nube sin autorización explícita.
- Una integración solo está "completa" tras una operación real de prueba verificada.
- Un plugin nuevo no debe requerir modificar el núcleo.
- Validar comandos (listas de argumentos, sin shell injection), limitar directorios, no exponer credenciales, registrar auditoría.
- La línea de tiempo unificada es la fuente de verdad.

## Diseño
Estudio de edición cinematográfico con identidad gaming. Tema oscuro, acento vibrante, superficies de vidrio sutil, fuente display + sans + mono, animaciones discretas, accesible y responsive.

## Forma de trabajar
Trabajar por fases. Verificar que cada fase funciona antes de avanzar. Al terminar, informar qué se hizo, cómo ejecutarlo, qué se probó y qué limitaciones quedan.

## Bitácora
- Leer `PROGRESS.md` al iniciar cada sesión: es la fuente del estado real del proyecto, sin depender del historial del chat.
- Al terminar cada fase, actualizar `PROGRESS.md` usando la plantilla de la última sección.
- No marcar una fase como completada sin haber verificado el resultado con comandos u operaciones reales.
