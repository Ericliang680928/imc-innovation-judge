@echo off
chcp 65001 >nul
title IMC 創新獎 AI 評審 - 安裝套件

echo ============================================================
echo   IMC 第 21 屆創新獎 AI 評審系統 - 套件安裝
echo ============================================================
echo.

REM 檢查 Python
where python >nul 2>nul
if errorlevel 1 (
    echo [錯誤] 找不到 Python,請先安裝 Python 3.10 以上版本。
    echo 下載:https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [步驟 1/3] 顯示 Python 版本
python --version
echo.

echo [步驟 2/3] 升級 pip
python -m pip install --upgrade pip
echo.

echo [步驟 3/3] 安裝相依套件(依 requirements.txt)
python -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo [錯誤] 套件安裝失敗,請查看上方錯誤訊息。
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ✅ 安裝完成!請執行 run.bat 啟動評審系統。
echo ============================================================
pause
