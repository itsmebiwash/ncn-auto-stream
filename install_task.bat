@echo off
echo ========================================================
echo   NEPAL CENTRAL NEWS - BACKGROUND TASK INSTALLER
echo ========================================================
echo.
echo This will setup the bot to run completely hidden in the 
echo background every 15 minutes.
echo.

schtasks /create /tn "NepalCentralNewsBot" /tr "wscript.exe \"%~dp0silent_runner.vbs\"" /sc minute /mo 15 /f

echo.
echo ========================================================
echo [SUCCESS] The task is now installed!
echo The bot will run automatically in the background as long
echo as this laptop is ON and connected to the internet.
echo.
echo If you ever want to remove it, open CMD and type:
echo schtasks /delete /tn "NepalCentralNewsBot" /f
echo ========================================================
pause
