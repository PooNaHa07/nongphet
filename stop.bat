@echo off
cd /d "%~dp0"
title Stop Nong Phet AI Assistant
chcp 65001 >nul

echo ========================================================
echo        Stopping Nong Phet AI Assistant...
echo ========================================================
echo.

echo [*] Closing Nong Phet Vision Daemon window...
taskkill /fi "WINDOWTITLE eq NongPhet Vision Daemon*" /f >nul 2>nul

echo [*] Closing Nong Phet Voice Server window...
taskkill /fi "WINDOWTITLE eq NongPhet Voice Server*" /f >nul 2>nul

echo [*] Freeing Port 5000 (Flask Web Server)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r ":5000\>"') do (
    taskkill /f /pid %%a >nul 2>nul
)

echo [*] Freeing Port 5002 (Vision Daemon)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r ":5002\>"') do (
    taskkill /f /pid %%a >nul 2>nul
)

echo [*] Freeing Port 8010 (Voice Server)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r "LISTENING" ^| findstr /r ":8010\>"') do (
    taskkill /f /pid %%a >nul 2>nul
)

echo.
echo ========================================================
echo [OK] ระบบน้องเพชรทุกเซอร์วิสหยุดการทำงานเรียบร้อยแล้ว
echo ========================================================
timeout /t 3 /nobreak >nul
