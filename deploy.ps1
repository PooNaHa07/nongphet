# ส่งโค้ดน้องเพชรไป Raspberry Pi 5 ผ่าน SSH (เรียก deploy_pi.sh ผ่าน Git Bash)
#   .\deploy.ps1                -> raspberrypi.local (หรือ 192.168.1.162)
#   .\deploy.ps1 192.168.1.50   -> ระบุที่อยู่เอง
#   .\deploy.ps1 --setup        -> ครั้งแรก: ส่งไฟล์ + ติดตั้งระบบบน Pi
# ต้องตั้ง SSH key ก่อน (ครั้งเดียว): ดู docs/SSH_KEY_SETUP.md
Set-Location $PSScriptRoot
& "C:\Program Files\Git\bin\bash.exe" deploy_pi.sh @args
