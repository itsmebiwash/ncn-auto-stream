import time
from datetime import datetime, timezone
from pymongo import ReturnDocument
from database.db_client import get_db
from config.settings import WORKER_INTERVAL_SECONDS
from facebook.publisher import post_to_facebook
from utils.cleanup import run_cleanup
from utils.heartbeat import record_laptop_heartbeat, is_laptop_active
import sys

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
    
    # Check if laptop is active when running on GitHub Actions
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("Checking if local laptop is active...")
        if is_laptop_active():
            print("  [OK] Local laptop is active! GitHub skipping worker run.")
            sys.exit(0)
            
    import os
    start_time = time.time()
    
    while True:
        try:
            # Record local laptop heartbeat
            record_laptop_heartbeat()
            # Run cleanup during idle loop
            run_cleanup()
            
            article = poll_queue()
            
            if article:
                print(f"Found article {article['_id']} with score {article.get('priority_score')}")
                
                success, fb_id_or_err = post_to_facebook(article)
                
                # REEL GENERATION AND PUBLISHING
                from utils.reel_generator import generate_news_reel
                from facebook.reels_publisher import post_reel_to_facebook
                import os
                
                reel_path = None
                reel_success = False
                reel_id = None
                
                if success and article.get('final_image_path') and os.path.exists(article['final_image_path']):
                    headline = article.get('english_headline', 'News')
                    out_reel = os.path.join("output", "ready_reels", f"{article['_id']}.mp4")
                    
                    print(f"Generating Reel for {article['_id']}...")
                    reel_path = generate_news_reel(article['final_image_path'], headline, out_reel)
                    
                    if reel_path:
                        print(f"Publishing Reel for {article['_id']}...")
                        reel_success, reel_id = post_reel_to_facebook(article, reel_path)
                
                if success:
                    db.articles.update_one(
                        {"_id": article["_id"]},
                        {"$set": {
                            "status": "posted", 
                            "facebook_post_id": fb_id_or_err,
                            "facebook_reel_id": reel_id,
                            "updated_at": datetime.now(timezone.utc),
                            "posted_at": datetime.now(timezone.utc)
                        }}
                    )
                    print(f"Successfully posted {article['_id']} to Facebook (Image & Reel).")
                    
                    # Move to posted directory
                    try:
                        import shutil
                        os.makedirs(os.path.join("output", "posted"), exist_ok=True)
                        if article.get('final_image_path') and os.path.exists(article['final_image_path']):
                            filename = os.path.basename(article['final_image_path'])
                            dest_path = os.path.join("output", "posted", filename)
                            shutil.move(article['final_image_path'], dest_path)
                            
                        # Move Reel
                        if reel_path and os.path.exists(reel_path):
                            os.makedirs(os.path.join("output", "posted_reels"), exist_ok=True)
                            reel_filename = os.path.basename(reel_path)
                            shutil.move(reel_path, os.path.join("output", "posted_reels", reel_filename))
                            
                    except Exception as e:
                        print(f"Failed to move files to posted folders: {e}")
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
