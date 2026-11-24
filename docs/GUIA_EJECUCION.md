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
foreach ($p in 8000,8011,8012,8017,8018,3000,3001,3017,3018,9000) {
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
2. Importar clips (dentro de GHS_WORKSPACE_DIR).
3. Colocar, mover, recortar, editar subtítulo, guardar, recargar y comprobar persistencia.
4. Provocar solapamiento: debe rechazarse con motivo.
5. "Renderizar con FFmpeg": esperar el trabajo, descargar y abrir el MP4.
6. "Generar borrador CapCut": desplegar la carpeta dfd_* a la carpeta de borradores y abrir CapCut.
7. "Enviar a Resolve" (puente iniciado): comprobar el clip en Resolve. Único paso sin prueba de clic real.
8. /backup: elegir carpeta, previsualizar, crear respaldo, verificar hashes, restaurar como copia.

## 6. Apagar
`detener-studio.bat` (cierra 8011, 3000 y 9000) o el bloque del paso 2.

## 7. Asistente de texto (Claude Code)

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
binario incluido por el SDK. No hay proceso extra que iniciar ni cambios en
`iniciar-studio.ps1`. Para configurar el backend, usa `GHS_AI_TIMEOUT_SECONDS`
(60 por defecto; máximo 300) y, opcionalmente, `GHS_AI_MODEL` (p. ej. `sonnet`).

- En **Extensiones**, pulsa **Verificar conexión con Claude**. Este botón envía
  un mensaje de prueba fijo (sin datos de proyecto) y exige una respuesta real.
- En un proyecto, pega un texto de guion o un SRT válido de hasta 12.000
  caracteres. Corregir conserva los tiempos; generar también requiere texto
  ya temporizado en SRT y permite subdividir sus intervalos. No hay
  transcripción de audio. La aplicación rechaza una salida SRT inválida,
  solapada o con tiempos fuera de los permitidos.
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
