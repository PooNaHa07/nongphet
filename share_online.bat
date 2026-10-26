@echo off
cd /d "%~dp0"
title Nong Phet AI - Public Online Tunnel

echo ========================================================
echo        Nong Phet AI - Public Internet Sharing
echo ========================================================
echo.
echo [*] Starting Cloudflare Tunnel for port 5000...
echo [*] 100%% Free, Secure HTTPS (SSL), No Registration Required!
echo.
echo [*] Look for the URL below (ending in .trycloudflare.com):
echo     Example: https://xxxx-xxxx-xxxx.trycloudflare.com
echo.
echo [*] You can open that link on your phone (4G/5G) or send
echo     it to judges and visitors anywhere in the world!
echo ========================================================
echo.

if not exist "cloudflared.exe" (
    echo [ERROR] cloudflared.exe not found in %~dp0
    pause
    exit /b 1
)

cloudflared.exe tunnel --url http://localhost:5000

if %errorlevel% neq 0 (
    echo.
    echo Tunnel stopped.
    pause
)
