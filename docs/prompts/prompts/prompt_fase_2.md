Lee AGENTS.md, SPEC.md y PROGRESS.md. La Fase 1 (Plugin Manager y pantalla Extensiones) ya está hecha y commiteada. Revisa el código existente y respeta su estructura. Hoy solo la FASE 2. No avances a la Fase 3. Al terminar, actualiza PROGRESS.md con la Fase 2 usando la plantilla.

Antes de escribir código, dime tu plan en pocas líneas.

Tareas de la Fase 2:

1. Excepciones y contrato de adaptadores (backend):
   - Crea CapabilityNotAvailable y errores tipados para: no conectado, plugin deshabilitado, operación inválida.
   - Crea la clase base abstracta EditorAdapter con los métodos de SPEC.md (connect, disconnect, health_check, get_capabilities, import_media, create_project, create_timeline, add_track, add_clip, update_clip, remove_clip, add_audio, add_subtitles, add_effect, render_preview, render_final, export_project, get_job_status).
   - Los métodos no soportados lanzan CapabilityNotAvailable. Nunca devuelven éxito falso.
   - Crea un registro de adaptadores que vincule cada plugin (por el ID de su manifiesto) con su clase de adaptador, de modo que agregar un plugin nuevo no requiera modificar el núcleo.
   - Un wrapper central debe llamar a get_capabilities() antes de ejecutar cualquier operación y rechazar las no soportadas.
   - No implementes adaptadores concretos todavía (FFmpeg es la Fase 3). Para probar el contrato, usa un adaptador de pruebas que viva solo en la carpeta de tests y que nunca aparezca en la app.

2. Modelo unificado de timeline (Pydantic v2):
   - Proyecto, escenas, recursos (assets), pistas (video, audio, subtítulos), clips, transiciones, audio, subtítulos, efectos y metadatos.
   - Conserva IDs de escenas y recursos, duraciones, posiciones y metadatos.
   - Validaciones: sin solapamientos inválidos en una pista, duraciones positivas, referencias a recursos existentes.
   - Serialización a JSON y persistencia en SQLite.
   - Define la interfaz base de conversores (Unified -> editor) con un resultado que incluya la lista de elementos que NO se pudieron exportar. Sin implementaciones concretas todavía.

3. EditingRouter:
   - Selecciona el plugin según operación solicitada, capacidades reales, editor instalado, estado de conexión, compatibilidad, coste y preferencias del usuario.
   - Reglas por defecto de SPEC.md (montaje automático -> FFmpeg, borrador editable -> VectCutAPI, edición profesional -> DaVinci Resolve, edición por transcripción -> Descript).
   - Permite selección manual del editor.
   - Nunca elige un plugin desconectado, deshabilitado o con dependencias ausentes. Si ninguno sirve, devuelve una explicación clara de por qué.
   - Plugins que envíen material a la nube (Descript) solo se eligen con autorización explícita del usuario.

4. API REST: endpoints para crear/leer/actualizar proyectos y su timeline, y un endpoint de decisión del router que reciba una operación y devuelva el plugin elegido, los descartados y el motivo de cada descarte (usando el estado real de los plugins).

5. Frontend (mínimo): en la pantalla Extensiones, añade una sección "Enrutador" que muestre, para cada tipo de operación, qué plugin se elegiría ahora mismo y por qué los demás se descartan, con datos reales del endpoint. Mismo estilo visual que lo existente.

6. Pruebas automáticas con pytest: contrato de EditorAdapter, validaciones del timeline, y casos del router (incluyendo que se rechace lo desconectado, lo deshabilitado y lo que enviaría datos a la nube sin autorización).

Al terminar: ejecuta pytest, lint, tsc y build, levanta los servidores y verifica el endpoint del router con el estado real de los plugins (FFmpeg conectado, Resolve instalado, CapCut y Descript con dependencias ausentes). Infórmame qué implementaste, qué probaste de verdad y qué limitaciones quedan.
