# SPEC: Plugin Ecosystem de Gaming History Studio

Especificación completa del proyecto. Se construye por fases (ver al final). Leer la sección de la fase en curso antes de empezar cada fase.

## Objetivo
Gaming History Studio actúa como centro de control que coordina editores de video externos (CapCut, DaVinci Resolve, FFmpeg, Descript) mediante plugins y servidores MCP. No desarrollar desde cero lo que pueda integrarse de forma segura con herramientas existentes.

## Principios no negociables
- Cero integraciones simuladas. Si un método no está soportado, devolver el error `CapabilityNotAvailable`; jamás simular éxito.
- Consultar `get_capabilities()` antes de ejecutar cualquier operación.
- No construir un editor de video completo (NLE).
- No enviar material a servicios en la nube sin autorización explícita del usuario.
- Una integración solo se declara "completa" cuando: se conectó realmente, se consultaron sus herramientas, se verificaron sus capacidades, se ejecutó una operación real de prueba, se verificó el resultado y se documentaron sus limitaciones.
- Agregar un plugin nuevo no debe requerir modificar el núcleo.

## Backend (FastAPI)

### Plugin Manager
Registrar, instalar/conectar, desconectar, activar/desactivar, listar herramientas y capacidades, verificar dependencias, mostrar errores y versiones, configurar credenciales, consultar requisitos de licencia y ejecutar diagnósticos.

Cada plugin tiene un manifiesto (JSON o YAML) validado con Pydantic:
`id, name, version, description, category, connection_type, mcp_command_or_endpoint, requirements, permissions, tools, capabilities, known_costs, documentation_url, install_status`.

### Interfaz EditorAdapter (clase base abstracta)
Métodos: `connect, disconnect, health_check, get_capabilities, import_media, create_project, create_timeline, add_track, add_clip, update_clip, remove_clip, add_audio, add_subtitles, add_effect, render_preview, render_final, export_project, get_job_status`.
Los métodos no soportados lanzan `CapabilityNotAvailable`.

### Adaptadores iniciales
1. **FFmpeg MCP:** inspección, corte, unión, conversión, escalado, overlays, subtítulos, mezcla de audio, efectos, renderizado. Es el backend local de respaldo.
2. **VectCutAPI / CapCut:** borradores, videos, imágenes, audio, textos, subtítulos, pistas, efectos y animaciones cuando estén soportados, guardado compatible con CapCut. Detectar instalación y versión de CapCut. No asumir que la estructura interna de los borradores es estable.
3. **DaVinci Resolve MCP:** conexión, inspección de proyectos, gestión de medios, timelines, clips, pistas, subtítulos, renders y trabajos. Detectar versión y edición. Distinguir capacidades de Free y Studio.
4. **Descript MCP (opcional, nunca obligatorio):** importar medios, consultar proyectos, pedir ediciones por instrucciones, subtítulos, exportar transcripciones y timelines, consultar trabajos. Informar requisitos de cuenta, costes y límites de exportación.

### Modelo unificado de timeline
Representación neutral e independiente del editor, con Pydantic. Es la **fuente de verdad** del proyecto. Conserva: IDs de escenas y recursos, duraciones, posiciones, pistas, transiciones, audio, subtítulos, efectos y metadatos.

Conversores: Unified → CapCut, Unified → DaVinci Resolve, Unified → FFmpeg, Unified → formatos de intercambio (por ejemplo OTIO/EDL/FCPXML). Cada conversor debe informar qué elementos no pudo exportar.

### EditingRouter
Selecciona el plugin según: operación solicitada, capacidades, editor instalado, estado de conexión, compatibilidad, coste y preferencias del usuario.
Reglas por defecto: montaje automático → FFmpeg; borrador editable → VectCutAPI; edición profesional → DaVinci Resolve; edición por transcripción → Descript. Permite selección manual.

### Seguridad
- Plugins desconocidos no son de confianza.
- Validar todo comando antes de ejecutarlo (listas de argumentos, sin shell injection).
- Mostrar permisos antes de instalar.
- Limitar el acceso a directorios permitidos.
- No exponer credenciales (cifradas o en variables de entorno; nunca en logs ni respuestas).
- Registro de auditoría de acciones.
- Confirmación para operaciones destructivas.
- Separar plugins locales y remotos.
- Interruptor para desactivar un plugin problemático.

## Frontend (Next.js) y diseño visual
Debe verse como un producto profesional y atractivo, no como un panel genérico.

**Dirección estética:** estudio de edición cinematográfico con identidad gaming. Tema oscuro por defecto (fondos casi negros con matiz azul/violeta), modo claro opcional. Un color de acento vibrante (violeta eléctrico o cian) usado con intención, más un acento secundario para estados. Superficies tipo vidrio sutil, bordes finos, sombras suaves con brillo en elementos activos. Tipografía distintiva: fuente display para títulos, sans legible para interfaz y monoespaciada para datos técnicos (vía `next/font`). Animaciones fluidas y discretas con Framer Motion (transiciones de página, entrada de tarjetas, skeletons de carga). Responsive y accesible (contraste, foco visible, teclado).

**Pantallas:**
1. **Dashboard:** resumen de documentales, trabajos recientes y estado de los plugins.
2. **Extensiones:** catálogo con pestañas Disponibles / Instalados / Conectados. Tarjetas de plugin con logo, versión, estado (indicador de color + texto), categoría y coste. Panel lateral de detalle con herramientas, capacidades, permisos, requisitos, configuración de credenciales y errores. Botón "Probar plugin" con resultado en vivo y botón "Ejecutar diagnóstico". Diálogo de permisos antes de instalar.
3. **Proyecto / Editor de supervisión:** línea de tiempo visual (pistas de video, audio y subtítulos, clips arrastrables con miniaturas, regla de tiempo, zoom). Panel para cambiar escenas, sustituir recursos, ajustar duraciones, modificar audio y editar subtítulos. Vista previa del render. Selector de editor (automático por el EditingRouter o manual). Acciones: "Enviar a editor externo", "Importar resultado", "Revisar render".
4. **Trabajos:** lista con progreso en tiempo real, logs y estados (en cola, ejecutando, completado, fallido).
5. **Auditoría/Seguridad:** registro de acciones y confirmaciones.

Si una capacidad no está disponible, la UI debe mostrarlo con claridad (botón deshabilitado con explicación), nunca ocultarlo ni fingir que funciona.

## Fases (en este orden)
1. Estructura del monorepo, Plugin Manager, manifiestos y base de datos. Pantalla Extensiones con datos reales.
2. Interfaz EditorAdapter, modelo de timeline unificado y EditingRouter.
3. Integración FFmpeg completa y verificada con una operación real (por ejemplo cortar y unir dos clips).
4. Integración VectCutAPI/CapCut verificada.
5. Integración DaVinci Resolve verificada.
6. Integración Descript opcional.
7. Editor visual integrado con la línea de tiempo.
8. Respaldo local de proyectos y restauración como copia. Los destinos remotos quedan fuera de esta fase.
9. Asistente de texto local de uso personal mediante Claude Agent SDK y la sesión de Claude Code de la PC. Solo un turno, sin herramientas ni MCP. Ningún texto se envía a Anthropic sin un clic explícito; solo se envía el texto pegado o el mensaje fijo del diagnóstico. Registrar operación y resultado sin guardar el contenido en auditoría. Previsualizar sugerencias de guion/cortes y de subtítulos SRT antes de permitir su aplicación.

## Criterio de éxito
Desde la app se debe poder: seleccionar un documental, elegir un editor, enviar recursos y timeline, ejecutar la edición vía plugin, recuperar el resultado, revisarlo, continuar en la app externa si corresponde y guardar/respaldar el proyecto.

## Entrega de cada fase
Al terminar cada fase informar: qué se implementó, cómo ejecutarlo, qué se probó realmente y qué limitaciones quedan. Si algo no pudo probarse (por ejemplo no hay DaVinci instalado), decirlo explícitamente en lugar de asumir que funciona.
