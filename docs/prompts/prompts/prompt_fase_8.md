Lee AGENTS.md, SPEC.md (sección de la Fase 8) y PROGRESS.md. Las Fases 1, 2, 3, 4, 5 y 7 están hechas; la 6 (Descript) es opcional y no se toca. Revisa el código existente y respeta su estructura y estilo visual. Hoy solo la FASE 8: respaldo de proyectos con DESTINOS A ELEGIR: carpeta local (predeterminado, sin nube) y Google Drive (opcional). Al terminar, actualiza PROGRESS.md con la Fase 8 usando la plantilla.

Antes de escribir código, dime tu plan en pocas líneas: qué sincronizas, cómo autenticas, dónde guardas credenciales y qué endpoints/pantallas añades. Lee la documentación oficial de la API de Google Drive y de OAuth para aplicaciones de escritorio/instaladas antes de decidir, y cita lo que confirmes.

Diseño: crea una abstracción de DESTINO DE RESPALDO (interfaz pequeña: listar respaldos, guardar, leer, y metadatos de estado) con dos implementaciones: (a) carpeta local, configurable por el usuario (por ejemplo otro disco, una carpeta de OneDrive o de Drive de escritorio), que es el destino por defecto y no usa red; (b) Google Drive por API, opcional. El usuario elige el destino por proyecto y puede tener ambos. El formato del respaldo es el mismo en los dos (carpeta o .zip con manifiesto de versión del esquema, fecha, hashes y el timeline JSON validado), de modo que un respaldo local se puede restaurar sin Drive. Añadir otro destino en el futuro no debe requerir tocar el núcleo.

Drive es la primera vez que la app enviaría datos a la nube. Reglas no negociables:
- Nada se sube sin autorización explícita del usuario. La sincronización está APAGADA por defecto, y cada subida muestra antes qué archivos van a subirse, su tamaño total y a qué carpeta de Drive. Sin confirmación no se sube nada.
- Alcance por defecto: SOLO proyectos y timelines (JSON validado) y metadatos de borradores/trabajos. Los vídeos, assets pesados y renders son opt-in por proyecto, con aviso del tamaño y cuota.
- Mínimo privilegio: usa el alcance de OAuth más estrecho que funcione (por ejemplo drive.file, que solo ve archivos creados por la propia app) en lugar de acceso a todo el Drive. Explica por qué lo elegiste.
- Credenciales: el client secret y los tokens de acceso/refresco NUNCA van en el repo, en logs, en la auditoría ni en respuestas de la API/UI. Guárdalos fuera del repo (por ejemplo en el directorio de configuración del usuario, con permisos restringidos) o en el almacén de credenciales del sistema si hay una opción razonable. Añade a .gitignore todo lo que pueda contenerlos y comprueba con git que no se versionan.
- Nunca borres ni sobrescribas archivos de Drive sin confirmación; las restauraciones no sobrescriben el proyecto local sin confirmación.
- Valida rutas (solo dentro de GHS_WORKSPACE_DIR), no uses shell, con timeouts, reintentos acotados y auditoría de cada operación (sin volcar contenido ni tokens).
- Como en las otras fases: cero simulación. Si algo no se puede verificar de verdad, repórtalo como limitación.

Tareas:

1. Diagnóstico previo: dime qué necesita el usuario para autenticar (proyecto en Google Cloud Console, pantalla de consentimiento en modo de pruebas, credenciales OAuth de tipo aplicación de escritorio) con pasos concretos y verificados contra la documentación oficial. Yo crearé las credenciales; no inventes valores. Si falta algo para continuar, DETENTE y dime exactamente qué.

2. Destinos de respaldo: implementa primero el destino local completo (con sus pruebas) y después Drive. Para Drive respeta la arquitectura de plugins (manifiesto + adaptador) si encaja; si Drive no es un editor, créalo como un servicio de respaldo separado del EditorAdapter, sin forzar el contrato de edición. Estado real: no configurado / autenticado / error. Flujo de autenticación local (loopback) iniciado por el usuario.

3. Sincronización:
   - Respaldar un proyecto (timeline JSON + metadatos) al destino elegido (carpeta local o carpeta dedicada de la app en Drive), con un manifiesto de respaldo (versión del esquema, fecha, hashes).
   - Listar respaldos disponibles en cada destino y restaurar un proyecto como COPIA nueva (no sobrescribir) tras validarlo con los mismos modelos Pydantic del timeline.
   - Detección de cambios por hash para no resubir lo igual; manejo claro de conflictos (no resolver en silencio: mostrar y preguntar).
   - Opt-in de assets pesados por proyecto, con tamaño estimado y confirmación.

4. API y frontend: pantalla "Respaldo" (o sección en Extensiones) con: selector de destino por proyecto (carpeta local / Drive), ruta de la carpeta local configurable con validación, estado de conexión con Drive, botón de conectar/desconectar, interruptor de sincronización por proyecto, vista previa de lo que se subirá con tamaño, botón de subir, lista de respaldos y restaurar como copia, historial/auditoría de operaciones. Mismo estilo visual. Nada hardcodeado: todo viene de la API.

5. Pruebas pytest: lógica de hashes, manifiesto, validación al restaurar, rechazo de rutas fuera del workspace, que los tokens no aparecen en logs ni respuestas, y que sin confirmación no se sube nada. Para la API de Google usa dobles SOLO en tests/ (nunca en la app) y pruebas en vivo que se omitan con skip claro sin credenciales.

6. VERIFICACIÓN REAL OBLIGATORIA. Primero con el destino local: respalda un proyecto de prueba a una carpeta, comprueba los archivos y hashes, restáuralo como copia y comprueba que el timeline restaurado es idéntico al original. Después con Drive, con una cuenta de prueba y la carpeta de prueba que yo indique: autenticar, subir un proyecto de prueba (sin vídeos), comprobar en Drive (consultando la API) que los archivos existen con el tamaño y hash esperados, restaurarlo como copia y comprobar que el timeline restaurado es idéntico. Verifica también que sin confirmación no se sube nada y que ningún token aparece en logs, auditoría, respuestas ni en git (muestra el comando usado). Usa el navegador real (Edge headless/Playwright) para el flujo de la UI donde sea posible; el consentimiento OAuth lo haré yo manualmente cuando me lo pidas.

Al terminar: pytest, lint, tsc, build, levanta los servidores y muéstrame la evidencia (comando -> resultado). Informa qué implementaste, qué probaste de verdad y qué limitaciones quedan. Commit "fase 8: respaldo local y en google drive" solo si hay verificación real; si no, commitea lo verificado y documenta el resto como parcial.
