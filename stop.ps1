# PowerShell script to stop all Nong Phet AI services
Clear-Host

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "       Stopping Nong Phet AI Assistant..." -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[*] Freeing ports 5000 and 5002..." -ForegroundColor Gray
$connections = Get-NetTCPConnection -LocalPort 5000, 5002 -ErrorAction SilentlyContinue
if ($connections) {
    foreach ($conn in $connections) {
        try {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        } catch {}
    }
}

# Stop any lingering python processes running vision_daemon or app_new
$processes = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "vision_daemon\.py|app_new\.py" }
if ($processes) {
    foreach ($p in $processes) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        } catch {}
    }
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "[OK] ระบบน้องเพชรทุกเซอร์วิสหยุดการทำงานเรียบร้อยแล้ว" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Start-Sleep -Seconds 2
