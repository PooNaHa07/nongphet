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

:: อ่านค่าที่ใช้ตัดสินใจจาก .env (เสียง / เซิร์ฟเวอร์เสียง / ค้นเว็บ)
set "TTS_ENGINE=edge"
set "VOICE_SERVER_URL="
set "HAS_GEMINI_KEY=0"
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        if /i "%%a"=="TTS_ENGINE" set "TTS_ENGINE=%%b"
        if /i "%%a"=="VOICE_SERVER_URL" set "VOICE_SERVER_URL=%%b"
        if /i "%%a"=="GEMINI_API_KEY" if not "%%b"=="" set "HAS_GEMINI_KEY=1"
    )
)
echo [INFO] Voice engine: %TTS_ENGINE%
if "%HAS_GEMINI_KEY%"=="1" (
    echo [INFO] Web search fallback: ON  (Gemini + Google Search, ต้องมีอินเทอร์เน็ต^)
) else (
    echo [INFO] Web search fallback: OFF (ไม่มี GEMINI_API_KEY ใน .env^)
)

:: Auto-start Local AI Engine (Ollama) if available
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    echo [*] Checking Local AI Engine - Ollama Qwen 2.5...
    tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
    if %errorlevel% neq 0 (
        echo [*] Starting Ollama serve...
        start /b "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve >nul 2>nul
    )
)

:: Pre-clean: ปิดโพรเซสค้างเก่าที่จองพอร์ต 5000 (แอป), 5002 (กล้อง), 8010 (เสียง) เพื่อป้องกันพอร์ตชน
echo [*] Freeing ports 5000, 5002 and 8010 if in use...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r "LISTENING" ^| findstr /r ":5000\> :5002\> :8010\>"') do (
    taskkill /f /pid %%a >nul 2>nul
)

:: เซิร์ฟเวอร์เสียง OmniVoice: เปิดเองเมื่อ .env ใช้ omnivoice และชี้มาที่เครื่องนี้
:: (ถ้าชี้ไปโน้ตบุ๊กเครื่องอื่น ให้เปิดเซิร์ฟเวอร์เสียงที่เครื่องนั้นแทน)
set "START_VOICE=0"
if /i "%TTS_ENGINE%"=="omnivoice" (
    echo %VOICE_SERVER_URL% | findstr /i "127.0.0.1 localhost" >nul && set "START_VOICE=1"
)
if "%START_VOICE%"=="1" (
    if exist "%~dp0.venv-voice\Scripts\python.exe" (
        echo [*] Starting OmniVoice voice server ^(Port 8010, โหลดโมเดล ~30 วินาที^)...
        start "NongPhet Voice Server" /min "%~dp0.venv-voice\Scripts\python.exe" tools\voice_server.py --host 127.0.0.1 --port 8010
    ) else (
        echo [WARN] ไม่พบ .venv-voice: ข้ามเซิร์ฟเวอร์เสียง ระบบจะใช้เสียงที่อัดไว้ล่วงหน้าเท่านั้น
    )
) else if /i "%TTS_ENGINE%"=="omnivoice" (
    echo [INFO] Voice server: %VOICE_SERVER_URL% ^(เครื่องอื่น^)
)

:: Auto-start Vision Daemon in a dedicated background window
echo [*] Starting Vision Daemon (Port 5002)...
start "NongPhet Vision Daemon" /min "%PY_BIN%" vision_daemon.py

timeout /t 2 /nobreak >nul

echo [*] Opening browser: http://localhost:5000  (จอหน้าตา: http://localhost:5000/emotion)
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
taskkill /fi "WINDOWTITLE eq NongPhet Voice Server*" /f >nul 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r "LISTENING" ^| findstr /r ":5002\> :8010\>"') do (
    taskkill /f /pid %%a >nul 2>nul
)
echo [*] Cleanup complete.
echo ========================================================
echo Press any key to close this window...
echo ========================================================
pause >nul
