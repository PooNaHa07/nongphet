@echo off
cd /d "%~dp0"
title Deploy NongPhet to Raspberry Pi 5

:: ============================================================
:: SSH KEY SETUP (ทำครั้งเดียวก่อนใช้งาน)
:: ดูรายละเอียดได้ที่ docs/SSH_KEY_SETUP.md
:: รองรับทั้ง pi@raspberrypi.local และ pi@192.168.1.162
:: ============================================================

set TARGET_HOST=raspberrypi.local
ping -n 1 -w 1000 %TARGET_HOST% >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] %TARGET_HOST% ไม่ตอบสนอง ลองเชื่อมต่อผ่าน 192.168.1.162...
    set TARGET_HOST=192.168.1.162
)

echo ========================================================
echo   Syncing NongPhet to Raspberry Pi 5 (%TARGET_HOST%)
echo ========================================================
echo.
echo [INFO] Target: pi@%TARGET_HOST%:~/nongphet/
echo [INFO] Using SSH key authentication (see docs/SSH_KEY_SETUP.md)
echo.

echo [*] Transferring source code via rsync (Git Bash)...
"C:\Program Files\Git\bin\bash.exe" -c "rsync -avz --progress --delete --exclude='venv/' --exclude='.venv/' --exclude='__pycache__/' --exclude='.git/' --exclude='*.pyc' --exclude='analytics_data.json' /d/nongphet/ pi@%TARGET_HOST%:~/nongphet/"

if %errorlevel% equ 0 (
    echo.
    echo [*] Transfer succeeded!
    echo [*] Restarting nongphet service on Raspberry Pi...
    ssh -t pi@%TARGET_HOST% "sudo systemctl restart nongphet && sudo systemctl status nongphet --no-pager"
    echo.
    echo ========================================================
    echo   Deploy Complete! NongPhet is running with latest code!
    echo ========================================================
) else (
    echo.
    echo [ERROR] Transfer failed! Please check network connection or SSH key setup.
    echo [INFO]  See docs/SSH_KEY_SETUP.md for instructions.
)

pause
