@echo off
cd /d "%~dp0"
title Deploy NongPhet to Raspberry Pi 5
chcp 65001 >nul
:: ส่งโค้ดไป Pi ผ่าน SSH (ไม่ต้องมี rsync) ใช้สคริปต์ deploy_pi.sh ผ่าน Git Bash
::   deploy.bat                 -> raspberrypi.local (หรือ 192.168.1.162)
::   deploy.bat 192.168.1.50    -> ระบุที่อยู่เอง
::   deploy.bat --setup         -> ครั้งแรก: ส่งไฟล์ + ติดตั้งระบบบน Pi
"C:\Program Files\Git\bin\bash.exe" deploy_pi.sh %*
pause
