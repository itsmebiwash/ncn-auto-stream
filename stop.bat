@echo off
title Stop Scraper Bot
echo [+] Attempting to stop the scraper and upload queue...
echo.

:: Kill the specific command prompt window running the bot
taskkill /F /FI "WINDOWTITLE eq Nepal News Scraper Bot*" /T >nul 2>&1

:: Also forcefully stop any rogue Python processes just in case
taskkill /F /IM python.exe /T >nul 2>&1

echo.
echo [+] All scraper tasks and uploads have been successfully stopped!
timeout /t 3 >nul
exit
