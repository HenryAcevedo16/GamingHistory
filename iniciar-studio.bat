@echo off
REM Gaming History Studio - doble clic para iniciar todo.
REM Debe estar en la misma carpeta que iniciar-studio.ps1 (raiz del repo).
REM Para no iniciar VectCutAPI: iniciar-studio.bat sinvectcut

if /i "%~1"=="sinvectcut" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar-studio.ps1" -SinVectCut
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar-studio.ps1"
)

REM Espera unos segundos a que el frontend arranque y abre el navegador.
timeout /t 8 /nobreak >nul
start "" "http://127.0.0.1:3000/extensions"
