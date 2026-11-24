Lee AGENTS.md, SPEC.md (sección de la Fase 7 y de pantallas) y PROGRESS.md. Las Fases 1, 2, 3, 4 y 5 están hechas (la 4 puede figurar como parcial hasta que el usuario confirme el borrador en CapCut; no la cierres tú). Revisa el código existente y respeta su estructura y estilo visual. Hoy solo la FASE 7: editor visual integrado con la línea de tiempo. No avances a la Fase 8. Al terminar, actualiza PROGRESS.md con la Fase 7 usando la plantilla.

Antes de escribir código, dime tu plan en pocas líneas, incluyendo qué pantallas y rutas vas a crear y qué endpoints nuevos necesitas.

Principio: la app NO es un editor de vídeo completo. El editor visual es una vista y edición ligera del timeline unificado (la fuente de verdad) y un panel para enviarlo a los editores reales mediante los adaptadores existentes. Toda la lógica de edición y validación sigue en el backend; el frontend solo la muestra y la dispara.

Alcance mínimo (hazlo bien antes de añadir nada más):

1. Lista de proyectos (/projects): proyectos reales del backend, crear proyecto, abrir, estados vacíos y de carga. Activa el elemento "Proyectos" de la barra lateral (hoy deshabilitado).

2. Pantalla de proyecto (/projects/[id]):
   - Panel de recursos (assets): lista de media importada con duración y tipo; importar por ruta local usando el endpoint existente (rutas dentro de GHS_WORKSPACE_DIR; muestra el error del backend si se rechaza).
   - Línea de tiempo visual: pistas de vídeo, audio y subtítulos con clips posicionados según start/duración reales, regla de tiempo, zoom horizontal y selección de clip.
   - Edición básica con el ratón y con teclado: añadir un asset a una pista, mover un clip, recortar inicio/fin, borrar, editar el texto de un subtítulo. Cada cambio se valida en el backend (solapamientos, duraciones, referencias): si el backend rechaza, muestra el motivo y revierte la vista; no valides solo en el cliente.
   - Guardado: usa el PUT del timeline existente; indica estado "guardado / cambios sin guardar / error". Deshacer y rehacer locales (al menos 20 pasos).
   - Panel "Enviar a": para cada editor (FFmpeg, DaVinci Resolve, CapCut) muestra, con datos reales del router y de las capacidades verificadas, si está disponible y por qué no; botones "Renderizar con FFmpeg", "Enviar a Resolve", "Generar borrador CapCut". Muestra los elementos no exportables (unsupported) que devuelve cada conversor ANTES de confirmar el envío. Nada se envía a la nube.
   - Trabajos: lista de renders/jobs del proyecto con estado real (queued/running/done/failed), enlace al resultado y log de error. Activa "Trabajos" en la barra lateral solo si lo implementas de verdad.

3. Backend: solo lo mínimo que falte (por ejemplo endpoints para operaciones de clip, o reutiliza el PUT del timeline). Mantén las reglas existentes: gate de conexión, listas cerradas, auditoría, sin credenciales en respuestas.

4. Diseño: mismo tema oscuro "gaming" ya existente, accesible (foco visible, roles ARIA, uso con teclado), responsive razonable (en móvil basta con ver el timeline en modo lectura). Animaciones discretas con Framer Motion y respeta prefers-reduced-motion. No hardcodees datos de ejemplo: todo viene de la API.

5. Pruebas: pytest para cualquier endpoint nuevo; pruebas del cliente para la lógica de timeline (posicionamiento, recorte, deshacer/rehacer) con el runner que ya use el frontend o uno ligero (vitest) si no hay ninguno; no añadas dependencias pesadas sin decírmelo.

6. VERIFICACIÓN REAL OBLIGATORIA: hasta ahora la UI solo se verificó por HTTP/build. Esta vez usa un navegador real (Playwright o Edge headless controlado) para ejecutar el flujo completo y guardar capturas:
   - crear un proyecto, importar dos clips generados con FFmpeg, colocarlos en la pista, recortar uno, guardar y recargar la página comprobando que el timeline persiste;
   - provocar un solapamiento y comprobar que el backend lo rechaza y la UI lo muestra;
   - lanzar "Renderizar con FFmpeg", esperar el job y comprobar con ffprobe que el archivo resultante dura lo esperado;
   - comprobar que "Enviar a Resolve" y "Generar borrador CapCut" muestran disponibilidad real según el estado de los plugins (si Resolve o VectCutAPI no están activos, el botón debe explicar por qué no se puede, no fallar en silencio).
   Muestra la evidencia (comando -> resultado y rutas de las capturas). Lo que no puedas probar de verdad, repórtalo como limitación.

Al terminar: pytest, lint, tsc y build, levanta los servidores y muéstrame la evidencia. Informa qué implementaste, qué probaste de verdad y qué limitaciones quedan. Commit "fase 7: editor visual" solo si hay verificación real; si no, commitea lo que esté verificado y documenta el resto como parcial.
