import argparse
import sys
import time
from database.db_client import init_db
from scrapers.nepali_scraper import run_scraper_cycle
from job_queue.worker import poll_queue
from facebook.publisher import post_to_facebook
from datetime import datetime, timezone

# Ensure Nepali characters print correctly on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def run_batch_mode(max_posts=3):
    print("Starting Batch Mode (GitHub Actions).")
    init_db()
    
    import os
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("Checking if local laptop is active...")
        from utils.heartbeat import is_laptop_active
        if is_laptop_active():
            print("  [OK] Local laptop is active! GitHub skipping run to avoid conflict.")
            sys.exit(0)
    
    # 1. Scrape, Dedupe, Groq Text & Vision, Render HTML Cards
    print("--- Running Scraper Cycle ---")
    run_scraper_cycle()
    
    # 2. Publish to Facebook
    print("--- Running Publishing Cycle ---")
    posted_count = 0
    from database.db_client import get_db
    db = get_db()
    
    while posted_count < max_posts:
        article = poll_queue()
        if not article:
            print("No more queued articles to post.")
            break
            
        print(f"Publishing article: {article.get('original_title', 'Unknown')}")
        success, fb_id_or_err = post_to_facebook(article)
        
        # Reel Generation & Publishing
        from utils.reel_generator import generate_news_reel
        from facebook.reels_publisher import post_reel_to_facebook
        import os
        
        reel_path = None
        reel_id = None
        
        if success and article.get('final_image_path') and os.path.exists(article['final_image_path']):
            headline = article.get('english_headline', 'News')
            out_reel = os.path.join("output", "ready_reels", f"{article['_id']}.mp4")
            
            print(f"Generating Reel for {article['_id']}...")
            reel_path = generate_news_reel(article['final_image_path'], headline, out_reel)
            
            if reel_path:
                print("Waiting 120 seconds before posting Reel to avoid spam...")
                time.sleep(120)
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
                    
                # Move reel
                if reel_path and os.path.exists(reel_path):
                    os.makedirs(os.path.join("output", "posted_reels"), exist_ok=True)
                    shutil.move(reel_path, os.path.join("output", "posted_reels", os.path.basename(reel_path)))
            except Exception as e:
                print(f"Failed to move image to posted folder: {e}")
                
            posted_count += 1
            if posted_count < max_posts:
                print("Sleeping 240 seconds before next post to avoid spam bans...")
                time.sleep(240)
        else:
            if "pause" in str(fb_id_or_err).lower():
                db.articles.update_one(
                    {"_id": article["_id"]},
                    {"$set": {"status": "queued", "updated_at": datetime.now(timezone.utc)}}
                )
                print("Meta Rate Limit reached. Halting batch publishing.")
                break
            else:
                db.articles.update_one(
                    {"_id": article["_id"]},
                    {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc)}}
                )
            print(f"Failed to post {article['_id']}: {fb_id_or_err}")
            time.sleep(5) # Small delay on failure before trying next
            
    print("Batch Mode execution completed. Exiting cleanly.")
    sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-mode", action="store_true", help="Run sequentially and exit (for CI/CD)")
    args = parser.parse_args()

    if args.batch_mode:
        run_batch_mode()
    else:
        print("Starting Continuous Local Mode (Every 1 Hour)")
        from utils.heartbeat import record_laptop_heartbeat
        while True:
            record_laptop_heartbeat()
            run_batch_mode()
            print("Finished run. Sleeping for 1 hour...")
            # We record heartbeat periodically during sleep
            for _ in range(60):
                record_laptop_heartbeat()
                time.sleep(60)
