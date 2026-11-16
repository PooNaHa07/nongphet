# PowerShell script to run Nong Phet AI (Modular 2026 Edition)
Clear-Host

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "       Starting Nong Phet AI Assistant..." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($ScriptDir) { Set-Location $ScriptDir }

$PythonExe = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    if (Test-Path ".\venv\Scripts\python.exe") {
        $PythonExe = ".\venv\Scripts\python.exe"
    } else {
        $found = Get-Command python -ErrorAction SilentlyContinue
        if ($found) { $PythonExe = $found.Source }
    }
}

if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] ไม่พบสภาพแวดล้อม Python หรือ .venv!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[INFO] Using Python: $PythonExe" -ForegroundColor Gray

# 1. Pre-clean: ปิดโพรเซสค้างเก่าที่จองพอร์ต 5000, 5002 หรือค้างล็อกกล้องเว็บแคม
Write-Host "[*] Freeing ports 5000, 5002 and cleaning background daemon processes..." -ForegroundColor Gray
$connections = Get-NetTCPConnection -LocalPort 5000, 5002 -ErrorAction SilentlyContinue
if ($connections) {
    foreach ($conn in $connections) {
        try {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        } catch {}
    }
}
try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "vision_daemon\.py" } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
} catch {}

# 2. Start Local AI Engine (Ollama) if installed and not running
$OllamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (Test-Path $OllamaExe) {
    if (-not (Get-Process -Name "*ollama*" -ErrorAction SilentlyContinue)) {
        Write-Host "[*] Starting Local AI Engine (Ollama Qwen 2.5)..." -ForegroundColor Magenta
        Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
    }
}

# 3. Start Vision Daemon in Background (Port 5002)
Write-Host "[*] Starting Vision Daemon (Port 5002)..." -ForegroundColor Cyan
$VisionProcess = Start-Process -FilePath $PythonExe -ArgumentList "vision_daemon.py" -WindowStyle Minimized -PassThru

# 4. Open browser
Start-Sleep -Seconds 2
Write-Host "[*] Opening browser at http://localhost:5000 ..." -ForegroundColor Green
Start-Process "http://localhost:5000"

# 5. Start Flask Server (Modular app_new.py)
Write-Host "[*] Starting Flask server (app_new.py)..." -ForegroundColor Yellow
Write-Host "[*] Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

try {
    & $PythonExe app_new.py
} finally {
    Write-Host "`n[*] Stopping background daemons..." -ForegroundColor Gray
    if ($VisionProcess -and -not $VisionProcess.HasExited) {
        try { $VisionProcess.Kill() } catch {}
    }
    $rem = Get-NetTCPConnection -LocalPort 5002 -ErrorAction SilentlyContinue
    if ($rem) {
        foreach ($c in $rem) {
            try { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
    Write-Host "[*] Cleanup complete." -ForegroundColor Green
}
