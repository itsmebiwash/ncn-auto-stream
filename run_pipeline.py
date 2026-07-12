import time
import shutil
import os
import sys
import argparse
from datetime import datetime, timezone

# Ensure Nepali characters print correctly on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from database.db_client import init_db, get_db
from scrapers.nepali_scraper import run_scraper_cycle, get_top_15_queued
from facebook.publisher import post_to_facebook
from facebook.reels_publisher import post_reel_to_facebook
from utils.reel_generator import generate_news_reel
from utils.heartbeat import record_laptop_heartbeat, is_laptop_active
from utils.cleanup import run_cleanup

# ── Constants ────────────────────────────────────────────────────────────────
SLOT_DURATION_SECONDS = 240   # Exactly 4 minutes per news item
REEL_POST_DELAY       = 15    # Seconds after image post before reel goes up
MAX_BATCH_POSTS       = 15    # Maximum articles per batch run


# ── Helpers ──────────────────────────────────────────────────────────────────
def _move_file(src, dest_dir):
    """Silently move a file to dest_dir. Creates dest_dir if needed."""
    try:
        if src and os.path.exists(src):
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(src, os.path.join(dest_dir, os.path.basename(src)))
    except Exception as e:
        print(f"  [Move Warning] {e}")


def _mark_posted(db, article, fb_post_id, reel_id=None):
    db.articles.update_one(
        {"_id": article["_id"]},
        {"$set": {
            "status": "posted",
            "facebook_post_id": fb_post_id,
            "facebook_reel_id": reel_id,
            "updated_at": datetime.now(timezone.utc),
            "posted_at":  datetime.now(timezone.utc)
        }}
    )


def _mark_failed(db, article, reason=""):
    db.articles.update_one(
        {"_id": article["_id"]},
        {"$set": {"status": "failed", "fail_reason": reason,
                  "updated_at": datetime.now(timezone.utc)}}
    )


def _mark_requeue(db, article):
    db.articles.update_one(
        {"_id": article["_id"]},
        {"$set": {"status": "queued", "updated_at": datetime.now(timezone.utc)}}
    )


def _generate_and_post_reel(article):
    """Generates the .mp4 reel and posts it to Facebook Reels. Returns (reel_path, reel_id)."""
    image_path = article.get("final_image_path")
    if not image_path or not os.path.exists(image_path):
        print("  [Reel] Skipped – card image not found.")
        return None, None

    slug = article.get("topic_slug", str(article["_id"]))
    os.makedirs(os.path.join("output", "ready_reels"), exist_ok=True)
    out_reel = os.path.join("output", "ready_reels", f"{slug}.mp4")

    headline = article.get("english_headline", "Nepal Central News")
    print(f"  [Reel] Generating reel → {os.path.basename(out_reel)}")
    reel_path = generate_news_reel(image_path, headline, out_reel)

    if not reel_path:
        print("  [Reel] Generation failed.")
        return None, None

    reel_success, reel_id = post_reel_to_facebook(article, reel_path)
    if reel_success:
        print(f"  [Reel] ✓ Published reel_id={reel_id}")
    else:
        print(f"  [Reel] ✗ Failed: {reel_id}")
        reel_id = None

    return reel_path, reel_id


# ── Core: process a single article in a 240-second slot ──────────────────────
def process_article_slot(article, slot_index, total, db):
    """
    Processes one article inside a strict 240-second (4-minute) window.

    T + 0s  : Post rendered 1080x1350 card image to Facebook Feed.
    T + 15s : Post 1080x1920 video reel to Facebook Reels.
    T + 15s → T + 240s : Sleep for remaining time.
    """
    slot_start = time.time()
    article_id = article["_id"]
    title_preview = article.get("original_title", "Unknown")[:70]

    print(f"\n{'='*65}")
    print(f"[SLOT {slot_index}/{total}] {title_preview}")
    print(f"  Priority: {article.get('priority_score', 'N/A')} | Source: {article.get('source_name', 'N/A')}")
    print(f"{'='*65}")

    # ── Step 1: Post image card ───────────────────────────────────
    print(f"  [T+0s] Posting image card to Facebook Feed...")
    success, fb_id_or_err = post_to_facebook(article)

    reel_path = None
    reel_id   = None

    if not success:
        if "pause" in str(fb_id_or_err).lower():
            print(f"  [!] Meta rate limit hit. Re-queuing article.")
            _mark_requeue(db, article)
            # Eat the remaining slot time to avoid hammering the API
            remaining = SLOT_DURATION_SECONDS - (time.time() - slot_start)
            if remaining > 0:
                time.sleep(remaining)
            return False, "rate_limit"
        else:
            print(f"  [!] Image post failed: {fb_id_or_err}")
            _mark_failed(db, article, reason=str(fb_id_or_err))
            return False, "image_fail"

    print(f"  [T+0s] ✓ Image card published. fb_post_id={fb_id_or_err}")

    # ── Step 2: Wait 15 seconds then post reel ────────────────────
    elapsed = time.time() - slot_start
    reel_delay = max(0, REEL_POST_DELAY - elapsed)
    if reel_delay > 0:
        print(f"  [Waiting {reel_delay:.0f}s before reel...]")
        time.sleep(reel_delay)

    print(f"  [T+{int(time.time()-slot_start)}s] Posting reel to Facebook Reels...")
    reel_path, reel_id = _generate_and_post_reel(article)

    # ── Step 3: Mark posted + move files ─────────────────────────
    _mark_posted(db, article, fb_id_or_err, reel_id)

    _move_file(article.get("final_image_path"), os.path.join("output", "posted"))
    if reel_path:
        _move_file(reel_path, os.path.join("output", "posted_reels"))

    print(f"  [✓] Article fully processed (Image + Reel).")

    # ── Step 4: Sleep for remainder of 240-second slot ───────────
    elapsed = time.time() - slot_start
    sleep_for = SLOT_DURATION_SECONDS - elapsed

    if sleep_for > 0:
        print(f"  [TIMER] Slot time remaining: {sleep_for:.1f}s. Sleeping until T+240s...")
        time.sleep(sleep_for)
    else:
        print(f"  [TIMER] Slot time fully consumed. Moving to next item immediately.")

    return True, fb_id_or_err


# ── Batch scheduler: runs Top-15 articles with 240s slots ────────────────────
def run_batch_schedule(max_posts=MAX_BATCH_POSTS):
    """
    Full batch mode:
    1. Runs scraper to fill the queue.
    2. Fetches Top-15 articles by priority_score.
    3. Posts each one in a strict 240-second dual-post slot.
    """
    print("\n" + "="*65)
    print("  NEPAL CENTRAL NEWS – AUTOMATED PUBLISHING ENGINE")
    print("="*65)

    init_db()

    # ── GitHub Actions: skip if laptop is locally active ─────────
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if is_laptop_active():
            print("[GitHub] Local laptop heartbeat detected. Skipping GitHub run.")
            sys.exit(0)

    # ── 1. Scrape all 50+ sources ─────────────────────────────────
    print("\n[Phase 1] Running Scraper Cycle across 50+ sources...")
    run_scraper_cycle()

    # ── 2. Fetch Top-15 queued articles ───────────────────────────
    print("\n[Phase 2] Fetching Top-15 articles by priority score...")
    top_articles = get_top_15_queued()

    if not top_articles:
        print("[Phase 2] No queued articles found. Nothing to post.")
        return

    print(f"[Phase 2] Found {len(top_articles)} articles. Starting 4-minute dual-post schedule.\n")
    db = get_db()

    posted_count = 0
    for index, article in enumerate(top_articles[:max_posts], start=1):
        # Mark as processing atomically
        db.articles.update_one(
            {"_id": article["_id"], "status": "queued"},
            {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}}
        )

        success, result = process_article_slot(article, index, len(top_articles[:max_posts]), db)

        if result == "rate_limit":
            print("[!] Rate limit hit. Stopping batch to protect quota.")
            break

        if success:
            posted_count += 1

    print(f"\n[Done] Batch complete. Published {posted_count} news items.")


# ── Continuous local mode: scrape hourly, post every 4 minutes ───────────────
def run_continuous_mode():
    """
    Local always-on mode:
    - Runs the scraper once every 60 minutes to refill the queue.
    - After each scrape, publishes all queued items using 240s slots.
    - Then sleeps until next hourly scrape cycle.
    """
    print("[Continuous] Starting Nepal Central News automation (local mode).")
    print("[Continuous] Schedule: scrape hourly, post every 4 minutes.\n")

    init_db()

    while True:
        record_laptop_heartbeat()
        run_cleanup()

        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting hourly cycle...")

        # Scrape
        print("[Phase 1] Running scraper across all 50+ sources...")
        run_scraper_cycle()

        # Fetch Top-15
        top_articles = get_top_15_queued()
        db = get_db()

        if not top_articles:
            print("[Queue] No articles to post. Sleeping 60 minutes until next scrape...")
        else:
            print(f"[Queue] {len(top_articles)} articles ready. Running 4-minute slots...\n")
            for index, article in enumerate(top_articles, start=1):
                record_laptop_heartbeat()

                # Mark as processing
                db.articles.update_one(
                    {"_id": article["_id"], "status": "queued"},
                    {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}}
                )

                success, result = process_article_slot(article, index, len(top_articles), db)

                if result == "rate_limit":
                    print("[!] Rate limit hit. Pausing remaining items until next cycle.")
                    break

        # Sleep until next hourly cycle (record heartbeat every minute during sleep)
        print("\n[Sleep] Waiting 60 minutes until next scrape cycle...")
        for _ in range(60):
            record_laptop_heartbeat()
            time.sleep(60)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nepal Central News Automated Publisher")
    parser.add_argument(
        "--batch-mode",
        action="store_true",
        help="Run one full scrape + Top-15 publish cycle then exit (for GitHub Actions / CI)."
    )
    args = parser.parse_args()

    if args.batch_mode:
        run_batch_schedule()
    else:
        run_continuous_mode()
