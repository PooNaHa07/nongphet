@echo off
cd /d "%~dp0"
title Train Nong Phet Intent Classifier

echo ========================================================
echo   Training Nong Phet Intent Classifier (Machine Learning)
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please make sure .venv folder exists.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" train_intent.py

echo.
echo ========================================================
echo Training process finished!
echo ========================================================
pause
