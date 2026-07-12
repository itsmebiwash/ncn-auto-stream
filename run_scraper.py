import time
from db.database import init_db
from scrapers.scraper_engine import run_scraper_cycle
from config.settings import SCRAPER_INTERVAL_HOURS

if __name__ == "__main__":
    print("Initializing Database...")
    init_db()
    
    print("Starting Hourly Scraper Engine...")
    while True:
        try:
            print("--- Running Scraper Cycle ---")
            run_scraper_cycle()
            print("--- Cycle Complete ---")
        except Exception as e:
            print(f"Scraper cycle error: {e}")
            
        import os
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print("Running in GitHub Actions - exiting after one cycle.")
            break
            
        sleep_seconds = SCRAPER_INTERVAL_HOURS * 3600
        print(f"Sleeping for {SCRAPER_INTERVAL_HOURS} hour(s) before next cycle...")
        time.sleep(sleep_seconds)
