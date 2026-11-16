# -*- coding: utf-8 -*-
"""
Compatibility entry point: app_new.py -> app.py
Ensures existing scripts (run.ps1, run.bat, setup_pi5.sh) continue to work seamlessly.
"""
from app import app, main

if __name__ == '__main__':
    main()
