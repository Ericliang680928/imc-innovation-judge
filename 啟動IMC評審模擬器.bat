@echo off
title IMC Innovation Judge Simulator

cd /d "%~dp0"

cls
echo.
echo ============================================================
echo            IMC 21st Innovation Award
echo               AI Judge Simulator
echo ============================================================
echo.
echo  [*] Starting up...
echo  [*] Browser will auto-open in ~6 seconds
echo  [*] URL: http://localhost:8501
echo  [*] To stop: close this window
echo.
echo ============================================================
echo.

REM --- Check Python ---
where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON

REM --- Check Streamlit ---
python -c "import streamlit" >nul 2>nul
if errorlevel 1 goto NEED_INSTALL

goto START_APP

:NO_PYTHON
echo.
echo [ERROR] Python not found.
echo Please install Python 3.10 or later from python.org
echo Make sure to check "Add Python to PATH" during install.
echo.
pause
exit /b 1

:NEED_INSTALL
echo.
echo [*] First-time setup detected.
echo [*] Installing required packages (2-5 minutes)...
echo.
python -m pip install -r requirements.txt
if errorlevel 1 goto INSTALL_FAILED
echo.
echo [OK] Packages installed.
echo.
goto START_APP

:INSTALL_FAILED
echo.
echo [ERROR] Package installation failed.
echo Try running manually: pip install -r requirements.txt
echo.
pause
exit /b 1

:START_APP
REM --- Auto-create .env from template if missing ---
if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul

REM --- Schedule browser to open after Streamlit starts ---
start "" cmd /c "timeout /t 6 /nobreak >nul 2>&1 && start http://localhost:8501"

REM --- Run Streamlit (foreground) ---
python -m streamlit run app.py --server.headless=true --server.port=8501 --browser.gatherUsageStats=false

echo.
echo ============================================================
echo  Streamlit server stopped.
echo ============================================================
echo.
pause
