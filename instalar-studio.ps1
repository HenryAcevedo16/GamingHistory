# Gaming History Studio - preparación en una PC nueva.
# Ejecuta (desde la raíz del repo):  .\instalar-studio.ps1
# Qué hace: revisa requisitos, crea el entorno de Python, instala dependencias
# del backend y del frontend, y crea backend\.env si no existe.
# Qué NO hace: no instala programas del sistema (Python, Node, Git, FFmpeg);
# te dice cuáles faltan y cómo instalarlos.

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$faltan = @()

function Tiene($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Estado($ok, $texto) {
    if ($ok) { Write-Host "[OK]    $texto" -ForegroundColor Green }
    else     { Write-Host "[FALTA] $texto" -ForegroundColor Red }
}

Write-Host "== Requisitos ==" -ForegroundColor Cyan
$py = Tiene "py"
Estado $py "Python (lanzador 'py')"
if (-not $py) { $faltan += "Python 3.12 o superior: winget install Python.Python.3.12  (marca 'Add to PATH')" }

$node = Tiene "node"; $npm = Tiene "npm"
Estado ($node -and $npm) "Node.js y npm"
if (-not ($node -and $npm)) { $faltan += "Node.js LTS: winget install OpenJS.NodeJS.LTS" }

$ff = Tiene "ffmpeg"; $fp = Tiene "ffprobe"
Estado ($ff -and $fp) "FFmpeg y ffprobe en el PATH"
if (-not ($ff -and $fp)) { $faltan += "FFmpeg: winget install Gyan.FFmpeg  (abre una PowerShell nueva después)" }

Estado (Tiene "git") "Git"
Estado (Tiene "claude") "Claude Code (opcional, para la IA)"
Estado (Tiene "opencode") "OpenCode (opcional, para la IA)"

if ($faltan.Count -gt 0) {
    Write-Host ""
    Write-Host "Instala lo que falta, abre una PowerShell nueva y vuelve a ejecutar este script:" -ForegroundColor Yellow
    $faltan | ForEach-Object { Write-Host " - $_" -ForegroundColor Yellow }
    exit 1
}

Write-Host ""
Write-Host "== Backend ==" -ForegroundColor Cyan
$backend = Join-Path $Repo "backend"
$venvPy = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Push-Location $backend
    py -m venv .venv
    Pop-Location
}
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r (Join-Path $backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de dependencias del backend." }

$envFile = Join-Path $backend ".env"
$envExample = Join-Path $backend ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "Creado backend\.env desde .env.example. Revísalo (carpeta de trabajo, contraseña de OpenCode)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "== Frontend ==" -ForegroundColor Cyan
Push-Location (Join-Path $Repo "frontend")
npm install
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Falló npm install." }
Pop-Location

Write-Host ""
Write-Host "== Comprobando manifiestos de plugins ==" -ForegroundColor Cyan
Push-Location $backend
& $venvPy -c "from app.plugins.registry import load_registry; from app.core.config import settings; s=load_registry(settings.resolved_plugins_dir); print(sorted(s.manifests)); print('Errores:', s.issues)"
Pop-Location

Write-Host ""
Write-Host "Listo. Siguiente: ajusta las rutas de iniciar-studio.ps1 si hace falta y ejecuta iniciar-studio.bat." -ForegroundColor Green
Write-Host "Opcional: 'claude auth login' y 'opencode auth login' para la IA." -ForegroundColor Cyan
