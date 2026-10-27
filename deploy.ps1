# ==============================================================================
# โครงการ: น้องเพชร AI Smart Guide
# สคริปต์: ซิงก์โค้ดและ Assets ไปยัง Raspberry Pi 5 (deploy.ps1)
# ==============================================================================

$PI_HOST = "192.168.1.162"
$PI_USER = "pi"
$PI_TARGET = "~/nongphet/"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Syncing NongPhet to Raspberry Pi 5 ($PI_HOST)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[INFO] Target: ${PI_USER}@${PI_HOST}:${PI_TARGET}" -ForegroundColor Yellow
Write-Host "[INFO] Password: nongphet999" -ForegroundColor Green
Write-Host ""

# ไฟล์และโฟลเดอร์ที่จำเป็นต้องซิงก์ (คัดเฉพาะของจริง ข้าม venv, .git, __pycache__)
$FILES_TO_SYNC = @(
    "app.py",
    "config.py",
    "intent_classifier.py",
    "semantic_retriever.py",
    "emotion_display.py",
    "esp32_listener.py",
    "local_slm.py",
    "knowledge_base.json",
    "model.pkl",
    "vectorizer.pkl",
    "templates",
    "static",
    "ml_artifacts"
)

Write-Host "[*] กำลังอัปโหลดไฟล์..." -ForegroundColor Yellow
$scpArgs = @("-r") + $FILES_TO_SYNC + @("${PI_USER}@${PI_HOST}:${PI_TARGET}")
& scp.exe $scpArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[*] อัปโหลดสำเร็จแล้ว!" -ForegroundColor Green
    Write-Host "[*] กำลังรีสตาร์ท Service 'nongphet' บนบอร์ด Raspberry Pi..." -ForegroundColor Yellow
    
    & ssh.exe -t "${PI_USER}@${PI_HOST}" "echo nongphet999 | sudo -S systemctl restart nongphet && sudo systemctl status nongphet --no-pager"
    
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "  Deploy สำเร็จเรียบร้อย! น้องเพชรพร้อมใช้งานโค้ดล่าสุดแล้ว" -ForegroundColor Green
    Write-Host "========================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[ERROR] การส่งไฟล์ขัดข้อง กรุณาตรวจสอบรหัสผ่านหรือการเชื่อมต่อ Wi-Fi" -ForegroundColor Red
}

