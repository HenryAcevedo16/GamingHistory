Lee AGENTS.md, SPEC.md (sección de la Fase 8) y PROGRESS.md. Las Fases 1, 2, 3, 4, 5 y 7 están hechas; la 6 (Descript) es opcional y no se toca. Revisa el código existente y respeta su estructura y estilo visual. Hoy solo la FASE 8, en su versión LOCAL: respaldo y restauración de proyectos en una carpeta del equipo. Google Drive queda explícitamente fuera de esta sesión (se hará más adelante); NO implementes Drive, OAuth ni nada que use la red. Al terminar, actualiza PROGRESS.md con la Fase 8 usando la plantilla y marca la parte de Drive como pendiente, no como hecha.

Antes de escribir código, dime tu plan en pocas líneas: formato del respaldo, dónde se configura la carpeta, qué endpoints y pantalla añades.

Diseño:
- Crea una abstracción pequeña de DESTINO DE RESPALDO (listar respaldos, guardar, leer, estado) con una sola implementación hoy: carpeta local. Debe permitir añadir otro destino (por ejemplo Drive) en el futuro sin tocar el núcleo, pero no escribas código especulativo de ese otro destino.
- Formato del respaldo: una carpeta o un .zip por respaldo con un manifiesto (versión del esquema, fecha, id y nombre del proyecto, hashes SHA-256 de cada archivo) y el timeline unificado en JSON validado. Metadatos de borradores y trabajos (rutas, ids, estados) como información, no como archivos binarios.
- Por defecto NO se incluyen vídeos, assets pesados ni renders. Opción por respaldo para incluir los assets referenciados, con aviso previo de tamaño total y espacio libre en disco, y confirmación explícita. Los assets incluidos conservan sus IDs; al restaurar se reubican en el workspace.

Reglas no negociables:
- La carpeta de destino la elige el usuario; valídala (existe o se puede crear, es escribible, no es una carpeta del propio repo ni del sistema, no está dentro de GHS_WORKSPACE_DIR de forma que el respaldo se respalde a sí mismo). Todas las operaciones de archivo usan rutas validadas: sin escapes con "..", sin seguir enlaces simbólicos fuera del destino.
- Nunca sobrescribas un respaldo existente sin confirmación; los nombres incluyen fecha/hora e id para no chocar.
- Restaurar crea un proyecto NUEVO (copia), nunca sobrescribe el proyecto local. Valida el timeline restaurado con los mismos modelos Pydantic y verifica los hashes del manifiesto antes de importar; si un hash no coincide, rechaza y explica cuál.
- Auditoría de cada operación (guardar, listar, restaurar, rechazos) sin volcar contenido de los archivos.
- Cero simulación: si algo no se puede verificar de verdad, repórtalo como limitación.

Tareas:
1. Backend: servicio de respaldo y restauración, destino local, endpoints REST (configurar carpeta, vista previa de lo que se guardará con tamaño, crear respaldo, listar respaldos, restaurar como copia). La configuración de la carpeta se guarda en la configuración existente (variables GHS_* y/o la base), no hardcodeada.
2. Frontend: pantalla "Respaldo" (activa el elemento en la barra lateral si encaja) con: carpeta de destino configurable y su validación, selector de proyecto, vista previa (archivos, tamaño, si incluye assets), botón "Crear respaldo", lista de respaldos con fecha/tamaño/estado de verificación de hashes y botón "Restaurar como copia", y el historial de operaciones. Mismo estilo visual, accesible, sin datos de ejemplo: todo viene de la API.
3. Pruebas pytest: formato y manifiesto, cálculo y verificación de hashes, rechazo de rutas inválidas o fuera de lugar, que no se sobrescribe nada sin confirmación, restauración como copia con timeline idéntico, rechazo de respaldos manipulados (un byte cambiado), y límite de tamaño/espacio.
4. VERIFICACIÓN REAL OBLIGATORIA: con el proyecto real de pruebas (el que tiene clips y subtítulo), crea un respaldo a una carpeta de prueba, lista los archivos y comprueba los hashes con un comando independiente (por ejemplo Get-FileHash); restáuralo como copia y comprueba que el timeline restaurado es idéntico al original (compara el JSON). Corrompe a mano un archivo del respaldo y comprueba que la restauración lo rechaza. Usa el navegador real (Edge headless/Playwright) para el flujo de la UI y guarda capturas. Muestra la evidencia (comando -> resultado).

Al terminar: pytest, lint, tsc, build, levanta los servidores y muéstrame la evidencia. Informa qué implementaste, qué probaste de verdad y qué limitaciones quedan. Commit "fase 8: respaldo local" solo si hay verificación real; si no, commitea lo verificado y documenta el resto como parcial.
