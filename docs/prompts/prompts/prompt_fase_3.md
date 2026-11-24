Lee AGENTS.md, SPEC.md y PROGRESS.md. Las Fases 1 y 2 ya están hechas y commiteadas. Revisa el código existente y respeta su estructura. Hoy solo la FASE 3 (integración FFmpeg). No avances a la Fase 4. Al terminar, actualiza PROGRESS.md con la Fase 3 usando la plantilla y rellena el hash del commit de la Fase 2 si falta.

Antes de escribir código, dime tu plan en pocas líneas.

Tareas de la Fase 3:

0. Deuda previa (hacer primero, con prueba cada una):
   - core/exec.py: haz que run_command pase env=minimal_env() al subprocess para que FFmpeg no herede las variables del backend. Añade una prueba que demuestre que una variable sensible del entorno no llega al proceso hijo.
   - editing/adapter.py: execute_operation no debe depender de que quien llama pase connected. Haz que el wrapper consulte el estado real de conexión del plugin (PluginManager/estado persistido) y rechace con PLUGIN_NOT_CONNECTED si no está conectado o está deshabilitado. Añade pruebas.

1. Adaptador FFmpeg (backend/app/editing/adapters/ffmpeg.py), registrado con @register_adapter("ffmpeg") sin importarlo desde el núcleo (el registro lo carga al arrancar, por ejemplo un módulo de autodescubrimiento en adapters/__init__.py):
   - Ejecuta ffmpeg/ffprobe SOLO a través de core/exec.py (lista de argumentos, sin shell, allowlist del manifiesto, timeout).
   - Valida rutas de entrada y salida: solo dentro de un directorio de trabajo configurable (GHS_*), sin rutas relativas que escapen (..), sin sobrescribir sin confirmación.
   - get_capabilities() devuelve solo lo que el adaptador implementa de verdad: import_media (ffprobe), create_project, create_timeline, add_clip, render_preview, render_final, get_job_status, export_project (según lo que realmente implementes). verified=True únicamente tras una operación real exitosa (guárdalo en estado, no lo pongas fijo).
   - Lo no implementado sigue lanzando CapabilityNotAvailable.
   - Convertidor Unified -> FFmpeg: traduce pistas de vídeo/audio del timeline a una cadena de comandos (cortar con -ss/-t, unir con concat, mezclar audio). Devuelve ConversionResult.unsupported con lo que no pudo exportar (transiciones, efectos, subtítulos si no los soportas).
   - Los renders son trabajos: crea un job con id, estado (queued/running/done/failed), progreso si es posible, log y ruta de salida, persistido en SQLite. get_job_status lee ese estado real.
   - Toda operación se audita en audit_log.

2. Router: ahora que existe el adaptador, `executable` y `adapter_registered` deben ser true para FFmpeg y las capacidades del router para FFmpeg deben salir de adapter.get_capabilities() (capability_source="adapter") cuando exista adaptador; si no, seguir con las del manifiesto. Actualiza las pruebas del router.

3. API REST: endpoints para importar media a un proyecto (ruta local), lanzar render (preview/final) de un proyecto, listar trabajos y consultar un trabajo. Confirmación explícita para sobrescribir archivos.

4. Frontend (mínimo): en Extensiones, en el panel de detalle de FFmpeg, mostrar capacidades "declaradas" vs "verificadas" con datos reales del endpoint. Mismo estilo visual.

5. Pruebas pytest: contrato del adaptador FFmpeg con ffmpeg real (omitir con skip claro si no está instalado), conversión Unified -> FFmpeg, rechazo de rutas fuera del directorio, jobs, y las dos deudas del punto 0.

6. VERIFICACIÓN REAL OBLIGATORIA (esto define si la Fase 3 está completa):
   - Genera con ffmpeg dos clips de prueba cortos (por ejemplo con lavfi testsrc y sine).
   - Crea un proyecto con esos dos assets, un timeline que CORTE un tramo de cada uno y los UNA en orden.
   - Lanza render_final por la API, espera el job y verifica con ffprobe que el archivo de salida existe, tiene la duración esperada (suma de tramos, con tolerancia) y los streams esperados.
   - Solo entonces marca la capacidad como verificada y enséñame get_capabilities() antes/después.
   - Si algo falla, no lo simules: repórtalo como limitación.

Al terminar: ejecuta pytest, lint, tsc y build, levanta los servidores y muéstrame la evidencia de la verificación real (comando -> resultado). Infórmame qué implementaste, qué probaste de verdad y qué limitaciones quedan. Haz commit con el mensaje "fase 3: adaptador ffmpeg" solo si todo lo anterior pasa.
