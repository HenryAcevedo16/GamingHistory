Lee AGENTS.md, SPEC.md y PROGRESS.md. Las Fases 1, 2, 3 y 5 están hechas y commiteadas. Revisa el código existente y respeta su estructura (adaptador FFmpeg y adaptador Resolve como referencia de patrón). Hoy solo la FASE 4 (integración VectCutAPI/CapCut). No avances a las Fases 6, 7 u 8. Al terminar, actualiza PROGRESS.md con la Fase 4 usando la plantilla.

Contexto del entorno:
- VectCutAPI está clonado FUERA de este repo en E:\VectCutAPI (no lo copies ni lo modifiques, no lo commitees). Corre con `python capcut_server.py` en un entorno virtual (venv-capcut) y escucha en http://127.0.0.1:9000 (puerto por defecto de la config actual; coincide con el manifiesto). Debe estar corriendo antes de las pruebas; si no responde, pídeme que lo inicie.
- CapCut de escritorio se instala aparte; sirve para abrir y revisar los borradores generados, pero VectCutAPI genera los borradores sin necesitarlo.
- VectCutAPI se basa en pyJianYingDraft y crea archivos de borrador de CapCut/Jianying. Lee su README y su documentación MCP/HTTP antes de diseñar el adaptador y cita lo que confirmes.

Antes de escribir código, dime tu plan en pocas líneas.

Reglas no negociables (las mismas de siempre):
- Cero integraciones simuladas: lo no soportado lanza CapabilityNotAvailable.
- get_capabilities() solo devuelve lo realmente implementado; verified=True únicamente tras una operación real exitosa guardada en estado.
- No enviar material a la nube sin autorización explícita. VectCutAPI puede tener funciones en la nube o de renderizado remoto: no las uses. Verifica y documenta que el flujo es 100% local y que el adaptador rechaza cualquier endpoint que no sea loopback salvo configuración explícita.
- Validar entradas (rutas dentro de GHS_WORKSPACE_DIR, sin escapar), sin shell injection, timeouts, auditoría de cada llamada. El endpoint no tiene autenticación: solo loopback.
- Agregar el plugin no debe modificar el núcleo: autodescubrimiento con @register_adapter("vectcut-capcut").

Tareas:

1. Diagnóstico previo con evidencia: confirma que el servidor responde en el endpoint (una llamada HTTP real, por ejemplo crear un borrador vacío y leer su respuesta), cuál es la carpeta donde guarda los borradores y si CapCut de escritorio está instalado y dónde. Si el servidor no responde o la API no permite lo esperado, DETENTE, documenta el bloqueo y no simules nada.

2. Adaptador VectCutAPI/CapCut (backend/app/editing/adapters/vectcut.py):
   - Habla con el servidor por HTTP local (cliente con timeout, errores tipados).
   - get_capabilities(): solo lo implementado y verificado (por ejemplo: crear borrador, añadir vídeo/audio/texto/subtítulos, guardar el borrador, exportar la ruta del borrador). Distingue "borrador editable generado" de "render final": VectCutAPI genera borradores para CapCut, no renderiza vídeo final; no declares render.final.
   - Convertidor Unified -> VectCutAPI que traduce pistas, clips, audio y subtítulos del timeline y devuelve en ConversionResult.unsupported lo que no pudo traducir (transiciones, efectos, etc. según lo que realmente soporte la API).
   - Los borradores generados se registran como resultados del proyecto (ruta, id del borrador, fecha) y se pueden consultar por la API.

3. Plugin Manager: la conexión solo se marca conectada si el servidor HTTP responde de verdad (check de canal no opcional). Manifiesto dirigido por datos; sin código específico en el núcleo. Si el endpoint por defecto necesita cambiar, que sea por variable VECTCUT_ENDPOINT, no hardcodeado.

4. Router y frontend: "Borrador editable" debe elegir VectCutAPI/CapCut únicamente si está conectado y con capacidades verificadas por el adaptador. En el detalle del plugin muestra declaradas vs. verificadas y la advertencia de que genera borradores, no renders.

5. Pruebas pytest: contrato del adaptador con un servidor HTTP simulado SOLO en tests/ (nunca en la app), conversión Unified -> VectCutAPI, rechazo de endpoints no locales y de rutas fuera del workspace, y pruebas de integración reales que se omiten con skip claro si el servidor no responde.

6. VERIFICACIÓN REAL OBLIGATORIA: con el servidor corriendo, genera con FFmpeg un clip de prueba, crea un proyecto con ese asset y un timeline simple (un clip de vídeo y un subtítulo), conviértelo y genera el borrador con el adaptador. Verifica leyendo el archivo de borrador en disco (no solo la respuesta HTTP) que existe y que contiene el clip y el subtítulo esperados. Después pídeme que lo abra en CapCut para confirmarlo visualmente y espera mi respuesta. Si algo falla, repórtalo como limitación; nunca como éxito.

Al terminar: pytest, lint, tsc y build, levanta los servidores y muéstrame la evidencia (comando -> resultado). Informa qué implementaste, qué probaste de verdad y qué limitaciones quedan. Commit "fase 4: adaptador vectcutapi capcut" solo si hay verificación real; si no, commitea solo la documentación del bloqueo.

Notas adicionales (leer antes de empezar):
- El CapCut instalado es la versión gratuita (internacional). Usa solo funciones gratuitas en las pruebas (clips, texto, subtítulos, audio básico); evita efectos, plantillas o materiales marcados como Pro.
- save_draft genera una carpeta dfd_* en el directorio donde corre capcut_server.py (E:\VectCutAPI). Para verla en CapCut hay que copiarla a la carpeta de borradores de CapCut (se ve en CapCut: engranaje -> Global Settings). El adaptador debe hacer esa copia solo cuando se lo ordene el usuario, y solo hacia esa carpeta; si no puedes determinar la ruta con certeza, pídemela. Lee la ruta de la configuración de CapCut o de config.json de VectCutAPI, y no escribas fuera de ella.
- Registra en la verificación la versión de CapCut y de VectCutAPI (commit del repo clonado). El formato interno de CapCut puede cambiar con actualizaciones; documenta esa fragilidad en PROGRESS.md y en el detalle del plugin en la UI.
- VectCutAPI genera borradores, no vídeo final: el render final se hace manualmente en CapCut. No declares render.final como capacidad.
- Aplica la misma disciplina de seguridad que en la Fase 5: si el adaptador usa una operación genérica, limítala con una lista cerrada de endpoints/métodos permitidos y audita los rechazos sin guardar el valor recibido.
- Las Fases 1, 2, 3 y 5 están cerradas (último commit de la Fase 5: 3471a88).
