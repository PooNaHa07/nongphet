@echo off
cd /d "%~dp0"
title Deploy NongPhet to Raspberry Pi 5

echo ========================================================
echo   Syncing NongPhet to Raspberry Pi 5 (192.168.1.162)
echo ========================================================
echo.
echo [INFO] Target: pi@192.168.1.162:~/nongphet/
echo [INFO] Password: nongphet999
echo.

echo [*] Transferring source code and web assets...
scp -r app.py config.py intent_classifier.py semantic_retriever.py emotion_display.py esp32_listener.py local_slm.py knowledge_base.json model.pkl vectorizer.pkl templates static ml_artifacts pi@192.168.1.162:~/nongphet/

if %errorlevel% equ 0 (
    echo.
    echo [*] Transfer succeeded!
    echo [*] Restarting nongphet service on Raspberry Pi...
    ssh -t pi@192.168.1.162 "echo nongphet999 | sudo -S systemctl restart nongphet && sudo systemctl status nongphet --no-pager"
    echo.
    echo ========================================================
    echo   Deploy Complete! NongPhet is running with latest code!
    echo ========================================================
) else (
    echo.
    echo [ERROR] Transfer failed! Please check network connection or password.
)

pause

pause