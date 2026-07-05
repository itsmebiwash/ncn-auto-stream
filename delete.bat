@echo off
echo ==============================================
echo Cleaning Output and Data Folders...
echo ==============================================

if exist output\*.png (
    del /Q output\*.png
    echo Deleted PNGs from output.
)

if exist output\posted\*.png (
    del /Q output\posted\*.png
    echo Deleted archived PNGs from output/posted.
)

if exist *.txt (
    del /Q *.txt
    echo Deleted text logs from root.
)

if exist data\scraped_history.json (
    del /Q data\scraped_history.json
    echo Deleted scraped_history.json
)

echo.
echo Cleanup Complete! All history and outputs wiped.
pause
