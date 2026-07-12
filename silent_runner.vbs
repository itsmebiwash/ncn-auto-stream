Set WshShell = CreateObject("WScript.Shell")

' Start the background worker (Queue Manager & Facebook Publisher)
WshShell.Run "python run_worker.py", 0, False

' Start the background scraper
WshShell.Run "python run_scraper.py", 0, False
