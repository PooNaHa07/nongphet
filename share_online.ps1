# PowerShell script to create Public Online Tunnel for Nong Phet AI
Clear-Host
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($ScriptDir) { Set-Location $ScriptDir }

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "       Nong Phet AI - Public Internet Sharing" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. ปิดโพรเซส cloudflared เก่าที่อาจค้างอยู่
Get-Process -Name cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# 2. ตรวจสอบ cloudflared.exe
$CloudflaredExe = ".\cloudflared.exe"
if (-not (Test-Path $CloudflaredExe)) {
    Write-Host "[*] กำลังดาวน์โหลด cloudflared.exe สำหรับใช้งานครั้งแรก..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $CloudflaredExe
}

if (-not (Test-Path $CloudflaredExe)) {
    Write-Host "[ERROR] ไม่สามารถดาวน์โหลด cloudflared.exe ได้ กรุณาตรวจสอบอินเทอร์เน็ต" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# 3. ตรวจสอบว่าระบบ Flask (พอร์ต 5000) เปิดอยู่หรือไม่
$PortCheck = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue
if (-not $PortCheck) {
    Write-Host "[!] พอร์ต 5000 ยังไม่ทำงาน กำลังเริ่มระบบ Nong Phet AI อัตโนมัติ..." -ForegroundColor Yellow
    $PythonExe = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
    Start-Process -FilePath $PythonExe -ArgumentList "app_new.py" -WindowStyle Minimized
    Start-Sleep -Seconds 3
}

Write-Host "[*] กำลังเชื่อมต่อ Cloudflare Tunnel (HTTPS ฟรี)..." -ForegroundColor Yellow
Write-Host "[*] คัดลอกลิงก์ https://xxxx.trycloudflare.com ด้านล่างไปเปิดบนมือถือได้เลยค่ะ" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

& $CloudflaredExe tunnel --edge-ip-version 4 --protocol http2 --url http://localhost:5000
