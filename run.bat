@echo off
cd /d "%~dp0"
title Nong Phet AI Assistant

echo ========================================================
echo        Starting Nong Phet AI Assistant...
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please make sure .venv folder exists.
    echo.
    pause
    exit /b 1
)

REM Auto-start Local AI Engine (Ollama) if available
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    echo [*] Starting Local AI Engine (Ollama Qwen 2.5)...
    start /b "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve >nul 2>nul
)

echo [*] Opening browser: http://localhost:5000 ...
start "" "http://localhost:5000"

echo [*] Starting Flask server...
echo [*] Press Ctrl+C to stop.
echo ========================================================
echo.

".venv\Scripts\python.exe" app.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code: %errorlevel%
    pause
)
