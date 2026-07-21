@echo off
title Nepal Central News - Manual Publisher UI

echo ==============================================
echo   Starting Manual Publisher Web Interface...
echo ==============================================

:: Check if virtual environment exists and activate it
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call .venv\Scripts\activate.bat
)

:: Ensure required packages are installed
echo [INFO] Checking dependencies (Flask, Werkzeug)...
pip install -r requirements.txt -q

echo [INFO] Starting Web Server...
echo [INFO] Once it says "Running on http://127.0.0.1:5000", open that link in your browser!
echo ==============================================

python manual_publisher\app.py

pause
