# ==============================================================================
# โครงการ: น้องเพชร AI Smart Guide
# สคริปต์: ซิงก์โค้ดและ Assets ไปยัง Raspberry Pi 5 (deploy.ps1)
# ==============================================================================
# SSH KEY SETUP (ทำครั้งเดียวก่อนใช้งาน): ดูรายละเอียดได้ที่ SSH_KEY_SETUP.md
# หากยังไม่มี SSH key ให้รัน: ssh-keygen -t ed25519 -C "nongphet-deploy"
# จากนั้น: ssh-copy-id pi@raspberrypi.local  (ใส่ password ครั้งสุดท้าย)
# ==============================================================================

$PI_HOST = if ($args[0]) { $args[0] } else { "raspberrypi.local" }
$PI_USER = "pi"
$PI_TARGET = "~/nongphet/"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Syncing NongPhet to Raspberry Pi 5 ($PI_HOST)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[INFO] Target: ${PI_USER}@${PI_HOST}:${PI_TARGET}" -ForegroundColor Yellow
Write-Host "[INFO] Using SSH key authentication (see SSH_KEY_SETUP.md)" -ForegroundColor Green
Write-Host ""

Write-Host "[*] กำลังอัปโหลดไฟล์ผ่าน rsync (Git Bash)..." -ForegroundColor Yellow

$rsyncCmd = "rsync -avz --progress --delete " +
    "--exclude='venv/' --exclude='.venv/' --exclude='__pycache__/' " +
    "--exclude='.git/' --exclude='static/audio/cache/' --exclude='*.pyc' " +
    "--exclude='analytics_data.json' " +
    "/d/nongphet/ ${PI_USER}@${PI_HOST}:${PI_TARGET}"

& "C:\Program Files\Git\bin\bash.exe" -c $rsyncCmd

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[*] อัปโหลดสำเร็จแล้ว!" -ForegroundColor Green
    Write-Host "[*] กำลังรีสตาร์ท Service 'nongphet' บนบอร์ด Raspberry Pi..." -ForegroundColor Yellow

    # NOTE: ถ้า SSH key ยังไม่ได้ตั้งค่า ให้แทนที่คำสั่งด้านล่างด้วย:
    # & ssh.exe -t "${PI_USER}@${PI_HOST}" "echo YOUR_PASSWORD | sudo -S systemctl restart nongphet && sudo systemctl status nongphet --no-pager"
    & ssh.exe -t "${PI_USER}@${PI_HOST}" "sudo systemctl restart nongphet && sudo systemctl status nongphet --no-pager"

    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "  Deploy สำเร็จเรียบร้อย! น้องเพชรพร้อมใช้งานโค้ดล่าสุดแล้ว" -ForegroundColor Green
    Write-Host "========================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[ERROR] การส่งไฟล์ขัดข้อง กรุณาตรวจสอบ SSH key หรือการเชื่อมต่อ Wi-Fi" -ForegroundColor Red
    Write-Host "[INFO]  ดูวิธีตั้งค่า SSH key ได้ที่ SSH_KEY_SETUP.md" -ForegroundColor Yellow
}
