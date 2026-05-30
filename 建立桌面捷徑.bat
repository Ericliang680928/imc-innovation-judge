@echo off
title Create Desktop Shortcut - IMC Judge Simulator

echo.
echo ============================================================
echo    Create "IMC Judge Simulator" Desktop Shortcut
echo ============================================================
echo.

setlocal

set "APP_DIR=%~dp0"
set "TARGET=%APP_DIR%啟動IMC評審模擬器.bat"
set "SHORTCUT_NAME=IMC 評審模擬器.lnk"

if not exist "%TARGET%" (
    echo  [ERROR] Target file not found:
    echo          %TARGET%
    echo.
    pause
    exit /b 1
)

echo  [*] App directory: %APP_DIR%
echo  [*] Creating shortcut...
echo.

REM --- Use PowerShell with REAL Desktop path (handles OneDrive redirect) ---
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$desktop = [Environment]::GetFolderPath('Desktop');" ^
    "Write-Host ('   [*] Real desktop path: ' + $desktop) -ForegroundColor Cyan;" ^
    "$shortcutPath = Join-Path $desktop '%SHORTCUT_NAME%';" ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$shortcut = $ws.CreateShortcut($shortcutPath);" ^
    "$shortcut.TargetPath = '%TARGET%';" ^
    "$shortcut.WorkingDirectory = '%APP_DIR%';" ^
    "$shortcut.Description = 'IMC 21st Innovation Award AI Judge Simulator';" ^
    "$shortcut.IconLocation = 'shell32.dll,167';" ^
    "$shortcut.WindowStyle = 1;" ^
    "$shortcut.Save();" ^
    "if (Test-Path $shortcutPath) {" ^
    "  Write-Host '   [OK] Desktop shortcut created!' -ForegroundColor Green;" ^
    "  Write-Host ('   [*] Path: ' + $shortcutPath) -ForegroundColor Gray;" ^
    "} else {" ^
    "  Write-Host '   [ERROR] Failed - try running as Administrator' -ForegroundColor Red;" ^
    "}"

echo.
echo ============================================================
echo   Done! Check your desktop for "IMC 評審模擬器"
echo   Double-click it anytime to launch the simulator.
echo ============================================================
echo.
pause
endlocal
