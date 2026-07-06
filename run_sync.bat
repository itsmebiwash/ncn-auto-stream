@echo off
cd /d "c:\Users\biwas\OneDrive\Desktop\Scrapper"
"C:\Users\biwas\AppData\Local\Programs\Python\Python314\python.exe" run_sync.py >> "%~dp0data\sync_log.txt" 2>&1
