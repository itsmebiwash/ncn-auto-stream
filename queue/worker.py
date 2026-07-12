import time
from datetime import datetime, timezone
from pymongo import ReturnDocument
from db.database import get_db
from config.settings import WORKER_INTERVAL_SECONDS
from facebook.publisher import post_to_facebook
from utils.cleanup import run_cleanup

def poll_queue():
    """
    Polls the highest priority queued article using find_one_and_update for atomicity.
    """
    db = get_db()
    
    try:
        article = db.articles.find_one_and_update(
            {"status": "queued"},
            {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}},
            sort=[("priority_score", -1), ("created_at", -1)],
            return_document=ReturnDocument.AFTER
        )
        return article
    except Exception as e:
        print(f"[Queue Error] {e}")
        return None

def start_worker():
    """
    Runs an infinite loop that polls the queue every X minutes.
    """
    print(f"Worker started. Interval: {WORKER_INTERVAL_SECONDS} seconds.")
    db = get_db()
    
    import os
    start_time = time.time()
    
    while True:
        try:
            # Run cleanup during idle loop
            run_cleanup()
            
            article = poll_queue()
            
            if article:
                print(f"Found article {article['_id']} with score {article.get('priority_score')}")
                
                success, fb_id_or_err = post_to_facebook(article)
                
                if success:
                    db.articles.update_one(
                        {"_id": article["_id"]},
                        {"$set": {
                            "status": "posted", 
                            "facebook_post_id": fb_id_or_err, 
                            "updated_at": datetime.now(timezone.utc),
                            "posted_at": datetime.now(timezone.utc)
                        }}
                    )
                    print(f"Successfully posted {article['_id']} to Facebook.")
                else:
                    if "pause" in str(fb_id_or_err).lower():
                        db.articles.update_one(
                            {"_id": article["_id"]},
                            {"$set": {"status": "queued", "updated_at": datetime.now(timezone.utc)}}
                        )
                    else:
                        db.articles.update_one(
                            {"_id": article["_id"]},
                            {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc)}}
                        )
                    print(f"Failed to post {article['_id']}: {fb_id_or_err}")
            else:
                print("Queue is empty. Waiting...")
                
        except Exception as e:
            print(f"[Worker Error] {e}")

        import os
        if os.environ.get("GITHUB_ACTIONS") == "true":
            elapsed = time.time() - start_time
            if elapsed > 1680: # 28 minutes
                print("Running in GitHub Actions - 28 minutes elapsed. Exiting gracefully.")
                break

        print(f"Sleeping for {WORKER_INTERVAL_SECONDS} seconds...")
        time.sleep(WORKER_INTERVAL_SECONDS)
