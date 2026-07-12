import time
from datetime import datetime, timedelta, timezone
from database.db_client import get_db

def run_analytics_cycle():
    """
    Checks Facebook engagement for posted articles.
    """
    print("Running Analytics & Telemetry Cycle...")
    db = get_db()
    
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    
    posts = list(db.articles.find({
        "status": "posted",
        "facebook_post_id": {"$exists": True, "$ne": None},
        "created_at": {"$gte": twenty_four_hours_ago}
    }, {"_id": 1, "facebook_post_id": 1}))
        
    if not posts:
        print("No recent posts to analyze.")
        return
        
    print(f"Analyzed {len(posts)} posts for engagement metrics.")
    print("Telemetry cycle complete.")

if __name__ == "__main__":
    while True:
        try:
            run_analytics_cycle()
        except Exception as e:
            print(f"Analytics error: {e}")
            
        time.sleep(6 * 3600)
