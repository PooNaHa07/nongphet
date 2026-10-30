@echo off
cd /d "%~dp0"
title Deploy NongPhet to Raspberry Pi 5

echo ========================================================
echo   Syncing NongPhet to Raspberry Pi 5 (raspberrypi.local)
echo ========================================================
echo.
echo [INFO] Target: pi@raspberrypi.local:~/nongphet/
echo [INFO] Password: nongphet999
echo.

echo [*] Transferring source code and web assets...
scp -r app.py config.py intent_classifier.py semantic_retriever.py emotion_display.py esp32_listener.py local_slm.py knowledge_base.json model.pkl vectorizer.pkl templates static ml_artifacts setup_ssl.sh start_kiosk.sh start_dual_screen.sh gunicorn.conf.py Procfile pi@raspberrypi.local:~/nongphet/

if %errorlevel% equ 0 (
    echo.
    echo [*] Transfer succeeded!
    echo [*] Restarting nongphet service on Raspberry Pi...
    ssh -t pi@raspberrypi.local "echo nongphet999 | sudo -S systemctl restart nongphet && sudo systemctl status nongphet --no-pager"
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