@echo off
title Stop IMC Judge Simulator

echo.
echo ============================================================
echo    Stop IMC Judge Simulator
echo ============================================================
echo.
echo  [*] Searching and stopping Streamlit processes...
echo.

powershell -NoProfile -Command ^
    "$procs = Get-Process python -ErrorAction SilentlyContinue;" ^
    "if ($procs) {" ^
    "  Write-Host ('   [*] Found ' + $procs.Count + ' Python process(es), stopping...');" ^
    "  $procs | Stop-Process -Force -ErrorAction SilentlyContinue;" ^
    "  Start-Sleep -Seconds 1;" ^
    "  Write-Host '   [OK] Stopped' -ForegroundColor Green;" ^
    "} else {" ^
    "  Write-Host '   [INFO] No running Python process found' -ForegroundColor Yellow;" ^
    "}"

echo.
echo ============================================================
echo  IMC Judge Simulator stopped.
echo  Next launch: double-click "IMC 評審模擬器" on Desktop
echo  or run "啟動IMC評審模擬器.bat" in app folder.
echo ============================================================
echo.
timeout /t 3 /nobreak >nul
