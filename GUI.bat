@echo off
title NCN Monitor Dashboard
cd /d "%~dp0"
echo Starting NCN Monitor Dashboard...
"C:\Users\biwas\AppData\Local\Programs\Python\Python314\python.exe" ncn_monitor.py
echo.
echo If the dashboard closed unexpectedly, see the error above.
pause
