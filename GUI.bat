@echo off
title NCN Infinite Scraper & Monitor
cd /d "%~dp0"
echo Starting NCN Infinite Execution Loop...
echo Setting Local Environment...

:: Start the python script that contains the infinite loop
start "NCN Background Worker" "C:\Users\biwas\AppData\Local\Programs\Python\Python314\python.exe" main.py

:: Optionally keep the monitor script running in the foreground
echo Starting NCN Monitor Dashboard...
"C:\Users\biwas\AppData\Local\Programs\Python\Python314\python.exe" ncn_monitor.py
echo.
echo Dashboard closed. (Background worker might still be running)
pause
