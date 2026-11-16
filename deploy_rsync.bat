@echo off
cd /d "%~dp0"
title Deploy NongPhet via rsync (Git Bash)

:: ============================================================
:: สคริปต์ Deploy โดยใช้ rsync ผ่าน Git Bash
:: รองรับ pi@raspberrypi.local และ pi@192.168.1.162
:: รวมคลังเสียง Pre-baked Audio Cache สำหรับรัน Offline 0ms
:: ============================================================

set TARGET_HOST=raspberrypi.local
ping -n 1 -w 1000 %TARGET_HOST% >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] %TARGET_HOST% ไม่ตอบสนอง ลองเชื่อมต่อผ่าน 192.168.1.162...
    set TARGET_HOST=192.168.1.162
)

echo ========================================================
echo   Deploy NongPhet to Raspberry Pi 5 (%TARGET_HOST%)
echo ========================================================
echo.
echo [INFO] Source : d:\nongphet\
echo [INFO] Target : pi@%TARGET_HOST%:~/nongphet/
echo [INFO] Excludes: venv/ .venv/ __pycache__/ .git/ *.pyc analytics_data.json
echo [INFO] Audio Cache : รวม static/audio/cache/ (58 ไฟล์ 0ms Offline)
echo.

echo [*] Starting rsync transfer...
"C:\Program Files\Git\bin\bash.exe" -c "rsync -avz --progress --delete --exclude='venv/' --exclude='.venv/' --exclude='__pycache__/' --exclude='.git/' --exclude='*.pyc' --exclude='analytics_data.json' /d/nongphet/ pi@%TARGET_HOST%:~/nongphet/"

if %errorlevel% equ 0 (
    echo.
    echo [*] rsync transfer complete!
    echo [*] Restarting nongphet service on Raspberry Pi...
    ssh -t pi@%TARGET_HOST% "sudo systemctl restart nongphet && sudo systemctl status nongphet --no-pager"
    echo.
    echo ========================================================
    echo   Deploy Complete! NongPhet is running with latest code!
    echo ========================================================
) else (
    echo.
    echo [ERROR] rsync failed! Please check:
    echo   1. Raspberry Pi เปิดเครื่องและเชื่อมต่อเน็ตแล้วหรือยัง (ping %TARGET_HOST%)
    echo   2. Git Bash ติดตั้งอยู่ที่ C:\Program Files\Git\
    echo   3. SSH key ตั้งค่าเรียบร้อย (ดู SSH_KEY_SETUP.md)
)

pause
