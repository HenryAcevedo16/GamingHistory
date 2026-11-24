@echo off
REM Gaming History Studio - cierra los servidores (backend 8011, frontend 3000, VectCutAPI 9000, OpenCode 4096 local).
REM No cierra DaVinci Resolve ni CapCut.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "foreach ($p in 8011,3000,9000,4096) { Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Where-Object { $p -ne 4096 -or ($_.LocalAddress -eq '127.0.0.1' -and (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName -like 'opencode*') } | ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction Stop; Write-Host \"Puerto $p cerrado (PID $($_.OwningProcess))\" } catch { Write-Host \"No se pudo cerrar el puerto $p\" } } }"

echo.
echo Listo. Las ventanas de PowerShell vacias puedes cerrarlas.
pause
