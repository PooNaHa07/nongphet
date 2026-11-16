@echo off
cd /d "%~dp0"
title Nong Phet AI Assistant
chcp 65001 >nul

echo ========================================================
echo        Starting Nong Phet AI Assistant...
echo ========================================================
echo.

:: Auto-detect Python Environment
set "PY_BIN="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_BIN=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_BIN=%~dp0venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set "PY_BIN=python"
    )
)

if "%PY_BIN%"=="" (
    echo [ERROR] ไม่พบสภาพแวดล้อม Python หรือ .venv!
    echo กรุณาตรวจสอบว่ามีโฟลเดอร์ .venv หรือติดตั้ง Python ในระบบ
    echo.
    pause
    exit /b 1
)

echo [INFO] Using Python: %PY_BIN%

:: Auto-start Local AI Engine (Ollama) if available
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    echo [*] Checking Local AI Engine - Ollama Qwen 2.5...
    tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
    if %errorlevel% neq 0 (
        echo [*] Starting Ollama serve...
        start /b "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve >nul 2>nul
    )
)

:: Pre-clean: ปิดโพรเซสค้างเก่าที่จองพอร์ต 5000 และ 5002 เพื่อป้องกันพอร์ตชน
echo [*] Freeing ports 5000 and 5002 if in use...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r ":5000\> :5002\>"') do (
    taskkill /f /pid %%a >nul 2>nul
)

:: Auto-start Vision Daemon in a dedicated background window
echo [*] Starting Vision Daemon (Port 5002)...
start "NongPhet Vision Daemon" /min "%PY_BIN%" vision_daemon.py

timeout /t 2 /nobreak >nul

echo [*] Opening browser: http://localhost:5000 ...
start "" "http://localhost:5000"

echo [*] Starting Flask server (app_new.py)...
echo [*] Press Ctrl+C to stop.
echo ========================================================
echo.

"%PY_BIN%" app_new.py

echo.
echo ========================================================
echo [*] Server stopped. Cleaning up background daemons...
taskkill /fi "WINDOWTITLE eq NongPhet Vision Daemon*" /f >nul 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r ":5002\>"') do (
    taskkill /f /pid %%a >nul 2>nul
)
echo [*] Cleanup complete.
echo ========================================================
echo Press any key to close this window...
echo ========================================================
pause >nul
