@echo off
cd /d "%~dp0"
title Nong Phet AI - Public Online Sharing
chcp 65001 >nul

echo ========================================================
echo        Nong Phet AI - Public Internet Sharing
echo ========================================================
echo.

:: 1. ปิดโพรเซส cloudflared เก่าที่อาจค้างอยู่
taskkill /f /im cloudflared.exe >nul 2>nul

:: 2. ตรวจสอบว่ามี cloudflared.exe หรือไม่
if not exist "%~dp0cloudflared.exe" (
    echo [*] กำลังดาวน์โหลด cloudflared.exe สำหรับใช้งานครั้งแรก...
    curl.exe -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -o "%~dp0cloudflared.exe" --progress-bar
)

if not exist "%~dp0cloudflared.exe" (
    echo [ERROR] ไม่สามารถดาวน์โหลด cloudflared.exe ได้ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ต
    pause
    exit /b 1
)

:: 3. ตรวจสอบว่าระบบ Nong Phet (Port 5000) เปิดอยู่หรือไม่
netstat -aon | findstr /r ":5000\>" >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] พอร์ต 5000 ยังไม่ทำงาน กำลังเริ่มระบบ Nong Phet AI อัตโนมัติ...
    if exist "%~dp0.venv\Scripts\python.exe" (
        start "NongPhet AI Server" /min "%~dp0.venv\Scripts\python.exe" app_new.py
    ) else (
        start "NongPhet AI Server" /min python app_new.py
    )
    timeout /t 3 /nobreak >nul
)

echo [*] เริ่มต้นสร้างอุโมงค์ออนไลน์ Cloudflare Tunnel (HTTPS ฟรี)...
echo [*] กรุณารอสักครู่ ระบบกำลังสร้างลิงก์สำหรับเปิดบนมือถือและส่งให้ผู้อื่น...
echo.
echo ========================================================
echo [URL จะแสดงด้านล่าง เป็นลิงก์ที่ลงท้ายด้วย .trycloudflare.com]
echo ========================================================
echo.

"%~dp0cloudflared.exe" tunnel --edge-ip-version 4 --protocol http2 --url http://localhost:5000

if %errorlevel% neq 0 (
    echo.
    echo Tunnel stopped.
    pause
)
