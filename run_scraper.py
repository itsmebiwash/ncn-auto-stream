import time
import os
import sys
from database.db_client import init_db
from scrapers.nepali_scraper import run_scraper_cycle
from config.settings import SCRAPER_INTERVAL_HOURS
from utils.heartbeat import record_laptop_heartbeat, is_laptop_active

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

if __name__ == "__main__":
    print("Initializing Database...")
    init_db()
    
    # Check if laptop is active when running on GitHub Actions
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("Checking if local laptop is active...")
        if is_laptop_active():
            print("  [OK] Local laptop is active! GitHub skipping scraper run.")
            sys.exit(0)
            
    print("Starting Hourly Scraper Engine...")
    while True:
        try:
            print("--- Running Scraper Cycle ---")
            record_laptop_heartbeat()
            run_scraper_cycle()
            print("--- Cycle Complete ---")
        except Exception as e:
            print(f"Scraper cycle error: {e}")
            
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print("Running in GitHub Actions - exiting after one cycle.")
            break
            
        sleep_seconds = SCRAPER_INTERVAL_HOURS * 3600
        print(f"Sleeping for {SCRAPER_INTERVAL_HOURS} hour(s) before next cycle...")
        time.sleep(sleep_seconds)

