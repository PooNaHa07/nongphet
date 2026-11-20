@echo off
cd /d "%~dp0"
title Nong Phet - Pre-bake Voice Cache
chcp 65001 >nul

echo ========================================================
echo   อัดเสียงน้องเพชรล่วงหน้า (Pre-bake Voice Cache)
echo ========================================================
echo   ใช้หลังแก้ฐานความรู้ / คำสั่งเสียง / ประโยคระบบ
echo   อัดเฉพาะประโยคที่ยังไม่มีเสียง (ของเดิมข้ามให้อัตโนมัติ)
echo.
echo   ตัวเลือก (ส่งต่อให้ prebake_tts.py):
echo     prebake.bat              อัดทุกภาษาที่ยังขาด
echo     prebake.bat --lang th    อัดเฉพาะภาษาไทย
echo     prebake.bat --force      อัดใหม่ทั้งหมด (ช้ามาก ใช้เมื่อเปลี่ยนเสียงต้นแบบ/seed)
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] ไม่พบ .venv\Scripts\python.exe
    pause
    exit /b 1
)

:: 1. เซิร์ฟเวอร์เสียง OmniVoice ต้องพร้อมก่อน (โน้ตบุ๊ก GPU เครื่องนี้ พอร์ต 8010)
set "STARTED_SERVER=0"
curl -s -m 3 http://127.0.0.1:8010/health | findstr /r /c:"ok.:true" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] เซิร์ฟเวอร์เสียงพร้อมอยู่แล้ว
    goto :bake
)
if not exist ".venv-voice\Scripts\python.exe" (
    echo [ERROR] เซิร์ฟเวอร์เสียงไม่ทำงาน และไม่พบ .venv-voice ในเครื่องนี้
    echo         ต้องรันไฟล์นี้บนโน้ตบุ๊ก GPU ที่มีเซิร์ฟเวอร์เสียง
    pause
    exit /b 1
)
echo [*] กำลังเปิดเซิร์ฟเวอร์เสียง (โหลดโมเดลประมาณ 30-60 วินาที)...
start "NongPhet Voice Server" /min ".venv-voice\Scripts\python.exe" tools\voice_server.py --host 0.0.0.0 --port 8010
set "STARTED_SERVER=1"
set /a WAITED=0
:wait_server
ping -n 4 127.0.0.1 >nul
set /a WAITED+=3
curl -s -m 3 http://127.0.0.1:8010/health | findstr /r /c:"ok.:true" >nul 2>&1
if %errorlevel% equ 0 goto :server_ready
if %WAITED% geq 180 (
    echo [ERROR] เซิร์ฟเวอร์เสียงไม่พร้อมภายใน 3 นาที ดูข้อความในหน้าต่าง "NongPhet Voice Server"
    pause
    exit /b 1
)
echo     ...รอ %WAITED% วินาที
goto :wait_server
:server_ready
echo [OK] เซิร์ฟเวอร์เสียงพร้อมแล้ว

:bake
echo.
echo [*] เริ่มอัดเสียง...
".venv\Scripts\python.exe" -X utf8 prebake_tts.py %*
set "BAKE_RESULT=%errorlevel%"

echo.
echo ========================================================
if "%BAKE_RESULT%"=="0" (
    echo   อัดเสียงเสร็จแล้ว ดูบรรทัด "สรุป" ด้านบน (ไม่สำเร็จ ต้องเป็น 0^)
) else (
    echo   [ERROR] อัดเสียงไม่สำเร็จ (exit %BAKE_RESULT%^)
)
echo.
echo   ขั้นต่อไป: ส่งไฟล์เสียงขึ้น Pi ด้วย deploy_pi.sh หรือ sync_audio_cache_to_pi.bat
if "%STARTED_SERVER%"=="1" echo   หมายเหตุ: เซิร์ฟเวอร์เสียงยังเปิดอยู่ (หน้าต่าง "NongPhet Voice Server"^) ปิดได้ถ้าไม่ใช้แล้ว
echo ========================================================
pause
exit /b %BAKE_RESULT%
