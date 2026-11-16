@echo off
cd /d "%~dp0"
title Run Automated Tests - Nong Phet AI

echo ========================================================
echo   Running Automated Test Suite for Nong Phet AI...
echo ========================================================
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_tests.py
) else (
    python run_tests.py
)

pause

