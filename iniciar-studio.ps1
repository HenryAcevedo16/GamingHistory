# Gaming History Studio - inicia los servidores en ventanas separadas.
# Ajusta las rutas de abajo a tu PC y ejecuta:  .\iniciar-studio.ps1
# Opciones:  -SinVectCut  (no inicia VectCutAPI)

param([switch]$SinVectCut)

$Repo      = "E:\GamingHistory"        # raíz del repo clonado
$VectCut   = "E:\VectCutAPI"           # carpeta de VectCutAPI
$ApiPort   = 8011                      # puerto del backend
$ApiUrl    = "http://127.0.0.1:$ApiPort"

function Probar-Puerto($puerto) {
    return [bool](Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue)
}

# Backend
if (Probar-Puerto $ApiPort) {
    Write-Host "Backend: el puerto $ApiPort ya está en uso, no se inicia otro." -ForegroundColor Yellow
} else {
    Start-Process powershell -WorkingDirectory "$Repo\backend" -ArgumentList @(
        "-NoExit", "-Command",
        ".\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort"
    )
    Write-Host "Backend iniciado en $ApiUrl"
}

# Frontend
if (Probar-Puerto 3000) {
    Write-Host "Frontend: el puerto 3000 ya está en uso, no se inicia otro." -ForegroundColor Yellow
} else {
    Start-Process powershell -WorkingDirectory "$Repo\frontend" -ArgumentList @(
        "-NoExit", "-Command",
        "`$env:NEXT_PUBLIC_API_URL='$ApiUrl'; npm run dev"
    )
    Write-Host "Frontend iniciado en http://127.0.0.1:3000/extensions"
}

# VectCutAPI (opcional)
if (-not $SinVectCut) {
    if (Probar-Puerto 9000) {
        Write-Host "VectCutAPI: el puerto 9000 ya está en uso, no se inicia otro." -ForegroundColor Yellow
    } else {
        Start-Process powershell -WorkingDirectory $VectCut -ArgumentList @(
            "-NoExit", "-Command",
            ".\venv-capcut\Scripts\python.exe capcut_server.py"
        )
        Write-Host "VectCutAPI iniciado en http://127.0.0.1:9000"
    }
}

Write-Host ""
Write-Host "Recuerda: para Resolve, ábrelo y ejecuta Workspace > Scripts > resolve_bridge." -ForegroundColor Cyan
