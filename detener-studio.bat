@echo off
REM Gaming History Studio - cierra los servidores (backend 8011, frontend 3000, VectCutAPI 9000).
REM No cierra DaVinci Resolve ni CapCut.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "foreach ($p in 8011,3000,9000) { Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction Stop; Write-Host \"Puerto $p cerrado (PID $($_.OwningProcess))\" } catch { Write-Host \"No se pudo cerrar el puerto $p\" } } }"

echo.
echo Listo. Las ventanas de PowerShell vacias puedes cerrarlas.
pause
