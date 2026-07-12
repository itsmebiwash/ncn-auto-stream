@echo off
:: NCN Auto-Start Script
:: This script starts the pipeline silently in the background at Windows login.
:: It is placed in the Windows Startup folder so it auto-runs on boot.

set "SCRIPT_DIR=%~dp0"
set "PYTHON=python"
set "LOG=%SCRIPT_DIR%logs\autostart.log"

:: Create logs directory if it doesn't exist
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

:: Check if already running
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I "python.exe" >NUL
if %ERRORLEVEL% == 0 (
    :: Check specifically for run_pipeline.py
    powershell -NoProfile -Command "Get-WmiObject Win32_Process -Filter 'name=''python.exe''' | Select-Object -ExpandProperty CommandLine" | findstr /I "run_pipeline.py" >NUL 2>&1
    if %ERRORLEVEL% == 0 (
        echo [%date% %time%] Pipeline already running. Skipping. >> "%LOG%"
        exit /b 0
    )
)

echo [%date% %time%] Auto-starting NCN pipeline... >> "%LOG%"

:: Start run_pipeline.py silently in background (no window)
start "" /B "%PYTHON%" "%SCRIPT_DIR%run_pipeline.py" >> "%LOG%" 2>&1

echo [%date% %time%] Pipeline started successfully. >> "%LOG%"
