@echo off
echo Generating live posting stats from MongoDB...
python update_stats.py
echo.
type posting_stats.txt
echo.
pause
