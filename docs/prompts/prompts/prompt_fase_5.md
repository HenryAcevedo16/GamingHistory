Lee AGENTS.md, SPEC.md y PROGRESS.md. Las Fases 1, 2 y 3 ya están hechas y commiteadas. Revisa el código existente y respeta su estructura. Hoy solo la FASE 5 (integración DaVinci Resolve); la Fase 4 (CapCut/VectCutAPI) queda pendiente por falta de instalación y no se toca. Al terminar, actualiza PROGRESS.md con la Fase 5 usando la plantilla.

Nota: hay una carpeta davinci-resolve-mcp-main/ sin trackear en la raíz. Es código de terceros. No la commitees ni la modifiques; si la usas, confirma su licencia y añádela a .gitignore o trátala como dependencia externa configurable (ruta por variable GHS_*).

Antes de escribir código, dime tu plan en pocas líneas.

Tareas de la Fase 5:

1. Diagnóstico real previo (sin escribir adaptador todavía):
   - Detecta la edición instalada de DaVinci Resolve (Free o Studio) y su versión, leyendo datos reales (ruta de instalación, metadatos del ejecutable o la propia API), no suposiciones.
   - Consulta la documentación oficial de scripting de Resolve (README de la API de scripting) y confirma qué se puede hacer desde fuera del programa en esa edición. Resume en pocas líneas qué es posible y qué no.
   - Comprueba si Resolve está abierto y si la API de scripting (RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB, fusionscript) es accesible desde Python. Si el scripting externo no está habilitado o la edición no lo permite, DETENTE aquí, documenta el bloqueo con evidencia en PROGRESS.md, marca la Fase 5 como "bloqueada" y no simules nada. Dime qué tendría que cambiar (por ejemplo, activar scripting externo en Preferencias o usar Studio).

2. Solo si el paso 1 confirma un canal vivo: adaptador DaVinci Resolve (backend/app/editing/adapters/resolve.py), autodescubierto con @register_adapter("davinci-resolve"):
   - Conexión real a la API de scripting (o al MCP davinci-resolve ya disponible), sin shell injection, con timeout y auditoría. No exponer credenciales.
   - get_capabilities() devuelve solo lo implementado y verificado de verdad (por ejemplo: crear proyecto, importar media al media pool, crear timeline, añadir clips, exportar/renderizar). verified=True solo tras una operación real exitosa, guardado en estado.
   - Lo no implementado lanza CapabilityNotAvailable. Distingue Free y Studio en las capacidades.
   - Convertidor Unified -> Resolve: informa en ConversionResult.unsupported lo que no pudo traducir.

3. Plugin Manager: la conexión de Resolve solo se marca conectada con un canal vivo verificado (hoy el check de canal es opcional y por eso se rechaza). Ajusta el manifiesto o los diagnósticos de forma genérica, sin código específico en el núcleo.

4. Router y frontend: "Edición profesional" debe elegir Resolve únicamente si está realmente conectado y con capacidades verificadas por el adaptador. Mostrar declaradas vs. verificadas en el detalle del plugin, igual que en FFmpeg.

5. Pruebas pytest: contrato del adaptador con un doble de pruebas solo en tests/, y pruebas reales de Resolve marcadas para omitirse con skip claro si Resolve no está disponible.

6. VERIFICACIÓN REAL OBLIGATORIA (define si la fase está completa): con Resolve abierto, crea un proyecto de prueba, importa un clip generado con FFmpeg, crea un timeline con ese clip y confirma leyendo el estado desde Resolve (no desde tu propio modelo) que el timeline y el clip existen. Muestra la evidencia comando -> resultado. Si no es posible, repórtalo como limitación o bloqueo; nunca como éxito.

Al terminar: pytest, lint, tsc y build, levanta los servidores y muéstrame la evidencia. Informa qué implementaste, qué probaste de verdad y qué limitaciones quedan. Haz commit "fase 5: adaptador davinci resolve" solo si hay verificación real; si la fase quedó bloqueada, commitea solo la documentación del bloqueo.
