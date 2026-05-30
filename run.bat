@echo off
chcp 65001 >nul
title IMC 創新獎 AI 評審系統

echo ============================================================
echo   🏆 IMC 第 21 屆創新獎 AI 評審系統
echo ============================================================
echo.
echo 正在啟動 Streamlit 網頁伺服器……
echo 啟動後會自動開啟瀏覽器,網址為 http://localhost:8501
echo.
echo (要關閉系統:回到此視窗按 Ctrl+C,或直接關閉視窗)
echo.

REM 切換到此 bat 所在目錄
cd /d "%~dp0"

REM 載入 .env(若存在)
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        set "%%a=%%b"
    )
    echo [INFO] 已載入 .env 環境變數
)

REM 啟動 Streamlit
python -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false

if errorlevel 1 (
    echo.
    echo [錯誤] 啟動失敗。請先執行 install.bat 安裝套件。
    pause
    exit /b 1
)
