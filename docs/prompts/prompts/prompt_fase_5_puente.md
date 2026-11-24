Lee AGENTS.md, SPEC.md y PROGRESS.md. Las Fases 1, 2 y 3 están hechas y commiteadas. La Fase 5 quedó BLOQUEADA porque la edición instalada es DaVinci Resolve 21.0.4 Free y el scripting externo (scriptapp("Resolve") desde un proceso externo) es solo de Studio. Hoy REINTENTAMOS la Fase 5 por otra vía: un PUENTE INTERNO que corre dentro de Resolve. Se sabe que esta vía funciona en la Free 21.0.x (otra app conectó un MCP a esta misma versión sin Studio). No avances a la Fase 4. Al terminar, actualiza PROGRESS.md (reemplaza el estado "bloqueada" de la Fase 5 por el resultado real, conservando la evidencia del diagnóstico anterior).

Antes de escribir código, dime tu plan en pocas líneas.

Contexto y reglas:
- La carpeta davinci-resolve-mcp-main/ (sin trackear, licencia MIT) contiene un puente para la edición gratuita. Lee su README y su código para entender cómo funciona (script que se ejecuta desde Workspace > Scripts dentro de Resolve y escucha en un puerto local). No la commitees. No copies su código al repo: úsala como referencia o dependencia externa configurable por variable GHS_*. Si necesitas escribir un script propio para Resolve, escríbelo tú, pequeño y revisable, y guárdalo en plugins/davinci-resolve/bridge/ con su propio README.
- El puente solo se puede iniciar manualmente desde el menú de Resolve (Workspace > Scripts). Eso no se puede automatizar sin riesgo: documenta el paso exacto para el usuario y haz que el adaptador diga claramente "puente no iniciado" si no hay respuesta.
- Es una vía frágil: funciona solo en Resolve Free 21.0.x y puede dejar de funcionar en 21.1+. Detecta la versión y edición, y repórtalas en las capacidades y en la UI. Si la versión es 21.1 o superior sin Studio, el adaptador debe declararse no disponible con ese motivo.
- SEGURIDAD (no negociable): el puente escucha SOLO en 127.0.0.1, con un token secreto generado al iniciar y guardado fuera del repo; rechaza conexiones sin token; NO ejecuta código arbitrario recibido por el socket: expone una lista cerrada de comandos (allowlist) con parámetros validados. Registra auditoría de cada llamada. No expongas el token en logs ni en la UI.

Tareas:

1. Diagnóstico del puente: lee la documentación del puente, confirma el puerto/protocolo y verifica que el script se puede lanzar en esta Resolve 21.0.4 Free (pídeme que lo inicie desde Workspace > Scripts cuando llegue el momento y espera mi confirmación). Comprueba con una llamada real (por ejemplo, leer la versión de Resolve y el nombre del proyecto abierto) que hay un canal vivo. Si no hay canal vivo, DETENTE, documenta con evidencia y no simules nada.

2. Adaptador DaVinci Resolve (backend/app/editing/adapters/resolve.py), autodescubierto con @register_adapter("davinci-resolve"), que habla con el puente por localhost:
   - get_capabilities() devuelve solo lo implementado y verificado de verdad (por ejemplo: leer estado, crear proyecto, importar media al media pool, crear timeline, añadir clips). verified=True solo tras una operación real exitosa, guardado en estado. Incluye edición/versión y modo "bridge" en las notas.
   - Lo no implementado lanza CapabilityNotAvailable.
   - Convertidor Unified -> Resolve que informa en ConversionResult.unsupported lo que no pudo traducir.
   - El adaptador solo puede ejecutar si el plugin está conectado (el gate central ya existe).

3. Plugin Manager: la conexión de Resolve solo se marca conectada con el canal vivo del puente verificado (check de canal NO opcional para esta vía). Hazlo dirigido por el manifiesto, sin código específico de Resolve en el núcleo.

4. Router y frontend: "Edición profesional" elige Resolve solo si está conectado y con capacidades verificadas por el adaptador. En el detalle del plugin muestra declaradas vs. verificadas, el modo "puente interno", la versión/edición y la advertencia de fragilidad.

5. Pruebas pytest: contrato del adaptador con un puente simulado SOLO en tests/ (nunca en la app), validación de la allowlist y del token, y pruebas reales de Resolve que se omiten con skip claro si el puente no responde.

6. VERIFICACIÓN REAL OBLIGATORIA: con Resolve abierto y el puente iniciado, crea un proyecto de prueba, importa un clip generado con FFmpeg, crea un timeline con ese clip y confirma leyendo el estado DESDE Resolve (no desde tu propio modelo) que el proyecto, el clip y el timeline existen. Muestra la evidencia comando -> resultado. Si algo falla, repórtalo como limitación; nunca como éxito.

Al terminar: pytest, lint, tsc y build, levanta los servidores y muéstrame la evidencia. Informa qué implementaste, qué probaste de verdad y qué limitaciones quedan. Commit "fase 5: adaptador davinci resolve (puente interno)" solo si hay verificación real; si no, commitea solo la documentación.
