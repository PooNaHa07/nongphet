@echo off
cd /d "%~dp0"
title Sync Pre-baked Audio Cache to Raspberry Pi 5
chcp 65001 >nul

echo ========================================================
echo   Sync Pre-baked Audio Cache to Raspberry Pi 5
echo ========================================================
echo.
echo [INFO] Local Cache : d:\nongphet\static\audio\cache\
echo [INFO] Remote Path : pi@raspberrypi.local:~/nongphet/static/audio/cache/
echo.

:: 1. ตรวจสอบ Git Bash สำหรับ rsync
if exist "C:\Program Files\Git\bin\bash.exe" (
    echo [*] กำลังซิงก์คลังเสียงด้วย rsync ผ่าน Git Bash...
    "C:\Program Files\Git\bin\bash.exe" -c "rsync -avz --progress /d/nongphet/static/audio/cache/ pi@raspberrypi.local:~/nongphet/static/audio/cache/ && rsync -avz /d/nongphet/static/audio/cache_manifest.json pi@raspberrypi.local:~/nongphet/static/audio/cache_manifest.json"
) else (
    echo [*] ไม่พบ Git Bash กำลังซิงก์ด้วย scp...
    scp -r static\audio\cache\* pi@raspberrypi.local:~/nongphet/static/audio/cache/
    scp static\audio\cache_manifest.json pi@raspberrypi.local:~/nongphet/static/audio/
)

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo   [SUCCESS] ซิงก์คลังเสียงไปยัง Raspberry Pi 5 สำเร็จ 100%!
    echo   Raspberry Pi 5 พร้อมทำงานโหมด Standalone 0ms แม้ไม่มีเน็ต
    echo ========================================================
) else (
    echo.
    echo [ERROR] การซิงก์ล้มเหลว กรุณาตรวจสอบ:
    echo   1. สัญญาณเครือข่าย: ping raspberrypi.local
    echo   2. สิทธิ์ SSH: ssh pi@raspberrypi.local
)

echo.
pause

