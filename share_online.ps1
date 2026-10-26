# PowerShell script to create Public Online Tunnel for Nong Phet AI
Clear-Host
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($ScriptDir) { Set-Location $ScriptDir }

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "       Nong Phet AI - Public Internet Sharing" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[*] Starting Cloudflare Tunnel for http://localhost:5000 ..." -ForegroundColor Yellow
Write-Host "[*] 100% Free, Secure HTTPS (SSL), No Registration Required!" -ForegroundColor Magenta
Write-Host ""
Write-Host "[*] Copy the https://xxxx.trycloudflare.com link below" -ForegroundColor Green
Write-Host "    and open it on your smartphone or share it with anyone!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$CloudflaredExe = ".\cloudflared.exe"
if (-not (Test-Path $CloudflaredExe)) {
    Write-Host "[ERROR] cloudflared.exe not found!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

& $CloudflaredExe tunnel --url http://localhost:5000
