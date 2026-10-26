# PowerShell script to run Nong Phet AI
Clear-Host

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "       Starting Nong Phet AI Assistant..." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($ScriptDir) { Set-Location $ScriptDir }

$PythonExe = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Virtual environment .venv not found!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Start Local AI Engine (Ollama) if installed and not running
$OllamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (Test-Path $OllamaExe) {
    if (-not (Get-Process -Name "*ollama*" -ErrorAction SilentlyContinue)) {
        Write-Host "[*] Starting Local AI Engine (Ollama Qwen 2.5)..." -ForegroundColor Magenta
        Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
    }
}

Write-Host "[*] Opening browser at http://localhost:5000 ..." -ForegroundColor Green
Start-Process "http://localhost:5000"

Write-Host "[*] Starting Flask server (Press Ctrl+C to stop)..." -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

& $PythonExe app.py
