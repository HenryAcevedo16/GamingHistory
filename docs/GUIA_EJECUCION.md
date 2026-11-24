# Gaming History Studio — Guía para correr y probar todo

Repo: https://github.com/HenryAcevedo16/GamingHistory  (local: E:\GamingHistory)

## Estado del proyecto
| Fase | Estado |
| --- | --- |
| 1 Plugin Manager y Extensiones | Hecha y verificada |
| 2 Adaptadores, timeline unificado, router | Hecha y verificada |
| 3 FFmpeg | Hecha y verificada |
| 4 VectCutAPI/CapCut | Hecha y verificada (borrador visto en CapCut 8.5 gratuito) |
| 5 DaVinci Resolve (puente interno, Free 21.0.4.5) | Hecha y verificada |
| 6 Descript | Opcional, sin empezar |
| 7 Editor visual | Hecha y verificada (Edge headless) |
| 8 Respaldo local | Hecha y verificada |
| 8 Google Drive | Pospuesta |
| 9 Asistente de texto | Verificado con Claude Code y SDK en Windows |
| 9b Proveedor OpenCode | Verificado con OpenCode 2.4.1 y un modelo de ChatGPT en Windows |
| 11 Visión bajo demanda | Verificada con OpenCode `openai/gpt-6.2-sol` y Claude Code en Windows |
| 10 Selector de archivos, orden de clips y notas | Subida y timeline verificados en Edge; respaldos y contexto de IA cubiertos por pruebas |

## 1. Preparar (una sola vez)
```powershell
cd E:\GamingHistory
git pull

cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..

cd frontend
npm install
cd ..
```

## 2. Cerrar servidores viejos
```powershell
foreach ($p in 8000,8011,8012,8017,8018,3000,3001,3017,3018,9000,4096) {
  Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force; "Cerrado $p" }
}
```

## 3. Iniciar la app
Copia `iniciar-studio.ps1`, `iniciar-studio.bat` y `detener-studio.bat` a la raíz del repo.
Revisa `$Repo` y `$VectCut` al inicio de `iniciar-studio.ps1`. Doble clic en `iniciar-studio.bat`.
- Backend: http://127.0.0.1:8011/api/health
- Frontend: http://127.0.0.1:3000/extensions
- VectCutAPI: http://127.0.0.1:9000

## 4. Activar editores externos
- FFmpeg: Extensiones -> instalar y conectar.
- DaVinci Resolve: abrir, abrir un proyecto guardado, Workspace > Scripts > resolve_bridge; luego instalar y conectar el plugin en Extensiones. No actualizar a la 21.1.
- CapCut: VectCutAPI corriendo (puerto 9000); instalar y conectar el plugin. CapCut cerrado hasta revisar un borrador.

## 5. Probar el flujo
1. /projects: crear proyecto.
2. Importar clips con **Elegir archivos** o **Importar por ruta local** (ver sección 8).
3. Colocar, mover, recortar, editar subtítulo, guardar, recargar y comprobar persistencia.
4. Provocar solapamiento: debe rechazarse con motivo.
5. "Renderizar con FFmpeg": esperar el trabajo, descargar y abrir el MP4.
6. "Generar borrador CapCut": desplegar la carpeta dfd_* a la carpeta de borradores y abrir CapCut.
7. "Enviar a Resolve" (puente iniciado): comprobar el clip en Resolve. Único paso sin prueba de clic real.
8. /backup: elegir carpeta, previsualizar, crear respaldo, verificar hashes, restaurar como copia.

## 6. Apagar
`detener-studio.bat` (cierra 8011, 3000, 9000 y OpenCode si escucha en
`127.0.0.1:4096`) o el bloque del paso 2, solo para puertos de Studio.

## 7. Asistente de texto

### Claude Code

En **cada PC** (trabajo y casa), instala o actualiza Claude Code y, con el mismo
usuario de Windows que abre Studio, ejecuta:

```powershell
claude --version
claude auth login
claude auth status
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Studio requiere una CLI instalada con `--restricted` y soporte de mensajes
`client_composed` (mínimo de protocolo 2.1.248; verificada con **2.1.319**). Si
Extensiones indica que esa CLI no admite el aislamiento, actualízala. Se comprobó
`claude-agent-sdk` 0.2.188 en el entorno real de Python 3.14.3. No configures
`ANTHROPIC_API_KEY` para Studio: usa la sesión `claude.ai` de Claude Code, no el
binario incluido por el SDK. Claude Code no requiere un servidor extra.
Para configurar el backend, usa `GHS_AI_TIMEOUT_SECONDS`
(60 por defecto; máximo 300) y, opcionalmente, `GHS_AI_MODEL` (p. ej. `sonnet`).

- En **Extensiones**, pulsa **Verificar conexión** en la tarjeta de Claude Code. Este botón envía
  un mensaje de prueba fijo (sin datos de proyecto) y exige una respuesta real.
- En un proyecto, pega un texto de guion o un SRT válido de hasta 12.000
  caracteres. Corregir conserva los tiempos; generar también requiere texto
  ya temporizado en SRT y permite subdividir sus intervalos. No hay
  transcripción de audio. La aplicación rechaza una salida SRT inválida,
  solapada o con tiempos fuera de los permitidos.
- Al pedir un **plan de guion y cortes**, se envían también el nombre de archivo, tipo,
  duración y nota guardada de cada recurso. Para **subtítulos**, se envían nombre,
  tipo y duración, **sin notas**. No se mandan archivos, rutas, IDs ni metadatos técnicos
  de los recursos. No escribas rutas ni secretos en las notas. La auditoría no guarda el texto.
- Tras revisar, guarda el plan textual en el proyecto (no cambia cortes) o
  añade los subtítulos como pista nueva. Para persistir la pista, pulsa
  **Guardar timeline**. También puedes descartar la propuesta.

Studio y los proyectos siguen en la PC, pero **la inferencia no es offline**:
Claude Code contacta a Anthropic cuando pulsas un botón de envío. No pegues
rutas, tokens ni contenido de `.env`. Studio no lee archivos para preparar el
mensaje y bloquea patrones sensibles comunes, pero no puede reconocer
credenciales arbitrarias pegadas como texto. Se desactivan herramientas,
MCP, habilidades, hooks y persistencia de sesión; el diagnóstico no sustituye
un aislamiento del sistema operativo frente a una CLI o políticas del equipo
no confiables. La auditoría SQLite solo guarda acción, estado y código de error.

Desde la raíz, ejecuta el diagnóstico real sin levantar servidores:

```powershell
.\backend\.venv\Scripts\python.exe scripts\verify_phase9.py
.\backend\.venv\Scripts\python.exe scripts\verify_phase9.py --suggestions
```

`--suggestions` también envía un guion y un SRT sintéticos. Usa una base SQLite
en memoria, sin tocar la base habitual. Ante un fallo devuelve **No verificado**
y un código de salida distinto de cero.

Referencias oficiales: [opciones de Python](https://code.claude.com/docs/en/agent-sdk/python#claudeagentoptions),
[configuración que no controla el SDK](https://code.claude.com/docs/en/agent-sdk/claude-code-features#what-settingsources-does-not-control)
y [autenticación del quickstart](https://code.claude.com/docs/en/agent-sdk/quickstart#setup).
El quickstart documenta API keys para integraciones y restringe ofrecer la
sesión o las cuotas de `claude.ai` en productos de terceros. Este flujo es
exclusivamente personal y local, no para distribución o servicio compartido.

### OpenCode (opcional)

1. En cada PC, instala **OpenCode V2** (probado con `2.4.1`) y confirma que
   `opencode --version` funciona en PowerShell. Con el mismo usuario de Windows que
   ejecutará Studio, corre `opencode auth login` y selecciona **OpenAI / ChatGPT**
   para usar tu sesión. `opencode auth list` permite revisar las cuentas sin exportar credenciales.
2. Crea o edita `backend/.env` (ignorado por Git) y asigna
   `GHS_OPENCODE_SERVER_PASSWORD` a una contraseña local fuerte. No es tu
   contraseña de ChatGPT. No la guardes en el frontend ni la pegues en un comando.
   Por defecto Studio usa `http://127.0.0.1:4096`. `GHS_OPENCODE_SERVER_URL` solo
   admite HTTP a `127.0.0.1`; el arranque automático siempre usa el puerto 4096.
   `GHS_OPENCODE_MODEL` es opcional: acepta el ID `proveedor/modelo` del catálogo.
   Si no se configura, debes cargar el catálogo y elegir un modelo en Studio.
   Studio nunca toma el predeterminado anunciado por el servidor OpenCode.
3. Desde la raíz, corre `.\iniciar-studio.ps1 -ConOpenCode` (puedes añadir
   `-SinVectCut`). El lanzador lee la contraseña desde `backend/.env`, la pasa
   solo en el entorno del proceso como `OPENCODE_SERVER_PASSWORD` y oculta la
   salida de `serve`, que puede imprimir el secreto. Si Studio ya estaba abierto,
   reinicia también el backend para cargar el `.env`. No expongas `serve` en la red.
4. En **Extensiones → OpenCode**, usa **Cargar modelos** para elegir uno, luego pulsa
   **Verificar conexión**. Envía un mensaje fijo al modelo elegido, o a
   `GHS_OPENCODE_MODEL` si no elegiste otro; no envía información del proyecto.
   En el asistente del proyecto, elige **OpenCode** y pulsa **Cargar modelos**.
   Se recuerdan el proveedor y el último modelo de OpenCode en ese navegador;
   el modelo guardado solo se reutiliza si sigue en el catálogo. Si desapareció,
   debes elegir otro. Cargar el catálogo o cambiar la selección no envía texto al
   proveedor. Antes de enviar un plan, revisa el modelo y el aviso sobre el
   guion y las notas que salen del equipo. Para Claude Code, el aviso muestra
   `GHS_AI_MODEL` si lo configuraste; si no, el modelo lo determina la CLI.

**Si no responde:** `AI_SERVER_UNAVAILABLE` indica que el proceso no escucha o
la conexión se interrumpió; revisa el puerto con `Get-NetTCPConnection -LocalPort 4096`
y vuelve a arrancar con `-ConOpenCode`. `AI_AUTH_FAILED` indica falta/rechazo de la
contraseña del servidor, un servidor sin protección, o autenticación ausente o
rechazada por el proveedor del modelo: lee el detalle antes de cambiar el `.env`
o repetir `opencode auth login`. `AI_MODEL_REQUIRED` pide cargar el catálogo y
elegir un modelo válido. `AI_PROVIDER_UNAVAILABLE` identifica el modelo con el
que falló la generación (HTTP 503); reintenta más tarde o elige otro.
Para `AI_TIMEOUT`, revisa la conexión del modelo o ajusta `GHS_AI_TIMEOUT_SECONDS`.

Prueba real con `opencode serve` en ejecución y sin tocar la base de proyectos:

```cmd
backend\.venv\Scripts\python.exe scripts\verify_phase9b.py
backend\.venv\Scripts\python.exe scripts\verify_phase9b.py --suggestions
```

Usa `--model <proveedor/modelo>` para elegir uno explícitamente; si se omite,
el script requiere `GHS_OPENCODE_MODEL`. Si no puede
contactar al servidor, autenticar o generar, termina con **No verificado** y
código distinto de cero. Al enviar texto, la inferencia puede salir de la PC
hacia el servicio del modelo elegido; lo local es la conexión de Studio a OpenCode.

Para comprobar solo la interfaz sin enviar texto a un proveedor, con Studio
en marcha, Python Playwright y Edge instalados:

```cmd
python scripts\verify_opencode_selection_ui.py --web http://127.0.0.1:3000
```

### Análisis de imágenes (Fase 11)

1. En **Proyectos → Recursos → Análisis de imágenes con IA**, elige el proveedor. Para
   OpenCode, pulsa **Cargar modelos** y elige uno con entrada de imagen. Solo aparecen
   los modelos que anuncian esa capacidad; no se sustituye tu elección por otro modelo.
2. Pulsa **Analizar** en una imagen o marca varias y pulsa **Analizar seleccionadas**.
   El diálogo muestra el destino, la cantidad, los bytes de las copias reducidas y los lotes.
   **Cancelar** no envía nada; **Enviar** comparte únicamente las copias JPEG con el proveedor.
   El límite es de 32 imágenes y 8 MB de JPEG por operación, en lotes de hasta 8 imágenes.
3. Revisa la propuesta. Puedes editarla, añadirla a la nota, reemplazar la nota o
   descartarla. Nada se guarda antes de aceptar. Los enlaces detectados se muestran como
   `[enlace omitido]`. Si el lote trae etiquetas incorrectas, se rechaza sin reenviarlo.

El original nunca se modifica. No se analizan vídeos ni audios. Cancelar durante el envío
detiene los siguientes lotes y solicita el cierre de la sesión de OpenCode; no deshace lo ya
enviado. Con Claude Code, el lote en curso puede terminar o llegar a su tiempo de espera,
pero se descarta su resultado y no se inician otros lotes.

Desde la raíz, con FFmpeg y OpenCode configurados, esta prueba **envía una imagen sintética**
por la misma ruta que Studio, sin tocar la base de proyectos:

```cmd
backend\.venv\Scripts\python.exe scripts\verify_phase11.py --model openai/gpt-6.2-sol
```

Añade `--claude` para enviarla también a Claude Code. Para probar solo la interfaz sin enviar
imágenes, con Playwright y Edge instalados, ejecuta `python scripts\verify_phase11_ui.py`.

## 8. Importar y ordenar recursos

1. En **Proyectos → Recursos**, pulsa **Elegir archivos** o suelta varios sobre la zona de
   importación. Puedes escribir una **nota opcional** junto a cada archivo antes de pulsar
   **Subir archivos**. Cada uno muestra su progreso y, si falla, su motivo. Cancelar detiene
   lo que reste del lote; los recursos ya guardados se quedan en el proyecto.
2. Para cambiar el orden usa **Subir** y **Bajar** (↑/↓ en la cola; Tab y Enter o Espacio
   funcionan igual que el ratón). La cola arranca en el orden que entrega el selector del
   navegador. Quitar una fila de la cola no borra la copia que ya importaste.
3. Elige la pista compatible y el **Inicio** de cada archivo:
   - **Después del anterior** es el modo inicial para vídeo, imágenes y audio narrado.
     La secuencia se añade al final de las pistas de destino y avanza en el orden de la
     cola, aunque cambie de vídeo a audio. Una imagen entra como un clip de 1 s.
   - Para música, en **Uso** selecciona **Música de fondo**. Pone **Empezar en 0** de
     forma predeterminada, sin inferir si el archivo contiene voz o música. Puedes cambiar
     el inicio manualmente para cualquier recurso. Los clips que empiezan en 0 no desplazan
     la secuencia y van a una pista nueva por defecto; también puedes elegir una pista
     compatible existente si su intervalo está libre.
   - Las pistas bloqueadas no se modifican. Si hay solapamiento en una misma pista, el lote
     no se coloca: cambia el inicio o el destino. Las pistas distintas pueden sonar a la vez.
4. Pulsa **Añadir todos en este orden**. Para reordenar clips ya colocados, selecciona uno y
   usa **Mover antes** o **Mover después**: mueve una posición y recompacta esa pista desde
   0 s, sin huecos ni solapes; no mueve otras pistas. Usa **Deshacer** o **Rehacer** para
   volver al estado anterior o recuperarlo. Pulsa **Guardar timeline** antes de salir.
5. Edita las notas en cada recurso y pulsa **Guardar nota**; borrar el texto la elimina.
   Admite hasta 500 caracteres en texto plano. Solo se envían al pedir un plan de IA.

### Archivos y espacio en disco

- El selector **copia** dentro de `GHS_WORKSPACE_DIR` y no modifica los originales. Usa
  nombres seguros y, si hay duplicados en el lote o el proyecto, añade un sufijo. Cada
  solicitud usa una subcarpeta propia. **Importar por ruta local** es la
  opción secundaria: solo acepta archivos que ya estén en el workspace y no hace otra copia.
- Extensiones de subida: MP4, MOV, M4V, MKV, WebM, AVI; M4A, MP3, WAV, FLAC, OGG, Opus;
  PNG, JPG/JPEG, WebP y BMP. Hace falta FFmpeg conectado para que `ffprobe` compruebe el
  contenido. Una extensión válida no basta; tampoco garantiza compatibilidad con todos los editores.
- El límite es **2 GiB por archivo** (2.147.483.648 bytes). Para cambiarlo, añade
  `GHS_UPLOAD_MAX_BYTES=<bytes>` a `backend/.env` y reinicia el backend.
- Prevé espacio para una copia completa por recurso: volver a subirlo consume espacio adicional.
  Un respaldo con medios vuelve a copiarlos. Ni quitar de la cola ni deshacer una colocación
  elimina archivos. Un cierre forzado del proceso o un corte eléctrico puede dejar una carpeta
  de subida sin publicar; Studio no borra carpetas automáticamente al reiniciar.
- El timeline unificado conserva los inicios guardados, pero el render FFmpeg aún advierte que
  no rellena huecos de vídeo ni mezcla varias pistas de vídeo. Revisa la comprobación previa
  al enviar a un editor.

### Mover un proyecto entre casa y trabajo

Mantén **la misma versión en ambas PC**: ejecuta `git pull` en las dos, instala las
dependencias actualizadas de `backend/requirements.txt` y reinicia Studio. Los respaldos
nuevos son **v2**; **no se pueden restaurar con versiones anteriores de Studio**. Esta
versión aún restaura v1, sin notas; los proyectos antiguos cargan con notas vacías y no
necesitan migración manual. No abras una SQLite ya guardada con el esquema nuevo en una
versión anterior. Para trasladar el proyecto, marca **Incluir archivos de
recursos** al crear el respaldo. Las notas se guardan como texto en el JSON y el manifiesto,
así que trata la carpeta del respaldo como material del proyecto.
Studio usa una sesión nueva con todos los permisos denegados, la generación
transitoria de texto (sin bucle de agente) y borra la sesión al terminar.
La auditoría de Studio tampoco guarda texto. Esta integración supone un servidor
OpenCode y una configuración local de confianza; no es un sandbox del sistema.

Referencias: [servidor](https://opencode.ai/docs/server), [SDK v2](https://opencode.ai/docs/sdk),
[API v2](https://opencode.ai/docs/api) y [autenticación del servidor](https://opencode.ai/docs/migrate-v1#server-authentication).

## Si algo falla
- Botón deshabilitado: abrir el detalle del plugin; indica el motivo.
- Frontend sin backend: revisar NEXT_PUBLIC_API_URL y el puerto del backend.
- Resolve no conecta: resolve_bridge debe estar corriendo y Resolve en 21.0.x.

## Pendientes conocidos
- Clic en "Enviar a Resolve" con el plugin activo (solo probado por API).
- Persistencia de la edición del subtítulo en CapCut tras guardar y reabrir.
- Más pruebas del cliente para el editor (hoy 3).
- SHA-256 detecta corrupción, no manipulación deliberada del manifiesto.
- Rendimiento del respaldo cerca de 20 GiB sin medir.
- Fase 6 (Descript) y respaldo en Google Drive.
