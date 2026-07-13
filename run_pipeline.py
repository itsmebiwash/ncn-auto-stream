"""
run_pipeline.py – Nepal Central News Automated Publisher

SCHEDULING LOGIC:
  - Each news cycle = 15 articles × 240 seconds = 3,600 seconds (60 minutes)
  - Scraper (Phase 1 + Phase 2) takes some time T_scrape
  - Next scrape is scheduled at: now + (60 min − T_scrape − 5 min buffer)
  - This ensures fresh content is ALWAYS ready before the queue runs dry.

EXAMPLE:
  10:00 AM  Scraper starts → takes 18 minutes
  10:18 AM  Top-15 images ready, posting begins (15 × 4 min = 60 min)
  10:37 AM  Next scrape auto-starts (60 - 18 - 5 = 37 min after posting starts)
  11:18 AM  Posting cycle ends, new images already waiting
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from database.db_client import init_db, get_db
from scrapers.nepali_scraper import (
    scrape_and_score_all, render_images_for_top_n,
    run_scraper_cycle, get_top_15_queued
)
from facebook.publisher import post_to_facebook
from facebook.reels_publisher import post_reel_to_facebook
from utils.reel_generator import generate_news_reel
from utils.heartbeat import record_laptop_heartbeat, is_laptop_active
from utils.cleanup import run_cleanup
from utils.logger import log_feedback

# ── Constants ─────────────────────────────────────────────────────────────────
SLOT_DURATION   = 240    # 4 minutes per news item (image + reel + sleep)
REEL_POST_DELAY = 15     # seconds after image post before reel goes up
TOP_N           = 15     # articles per posting cycle
CYCLE_MINUTES   = 60     # total cycle window in minutes
BUFFER_SECONDS  = 300    # 5 min buffer before next scrape


# ── Helpers ───────────────────────────────────────────────────────────────────
def _delete(path: str) -> None:
    """Instantly delete a local file after it has been posted. Zero storage waste."""
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f'  [Cleanup] Deleted: {os.path.basename(path)}')
    except Exception as e:
        print(f'  [Cleanup Warning] Could not delete {path}: {e}')


def _mark_posted(db, article, fb_post_id, reel_id=None):
    try:
        db.articles.update_one(
            {'_id': article['_id']},
            {'$set': {
                'status':          'posted',
                'facebook_post_id': fb_post_id,
                'facebook_reel_id': reel_id,
                'updated_at':       datetime.now(timezone.utc),
                'posted_at':        datetime.now(timezone.utc)
            }}
        )
    except Exception as e:
        print(f'  [DB Error] Failed to mark posted: {e}')


def _mark_failed(db, article, reason=''):
    try:
        db.articles.update_one(
            {'_id': article['_id']},
            {'$set': {'status': 'failed', 'fail_reason': reason,
                      'updated_at': datetime.now(timezone.utc)}}
        )
    except Exception as e:
        print(f'  [DB Error] Failed to mark failed: {e}')


def _mark_requeue(db, article):
    try:
        db.articles.update_one(
            {'_id': article['_id']},
            {'$set': {'status': 'queued', 'updated_at': datetime.now(timezone.utc)}}
        )
    except Exception as e:
        print(f'  [DB Error] Failed to requeue: {e}')


def _post_pre_rendered_reel(article):
    reel_path = article.get('final_reel_path')
    if not reel_path or not os.path.exists(reel_path):
        print('  [Reel] Skipped – pre-rendered reel not found.')
        return None, None

    reel_success, reel_id = post_reel_to_facebook(article, reel_path)
    if reel_success:
        print(f'  [Reel] ✓ Published reel_id={reel_id}')
    else:
        print(f'  [Reel] ✗ Failed: {reel_id}')
        reel_id = None

    return reel_path, reel_id


def pre_render_reels(articles):
    print(f"\n[Pre-Render] Generating reels for {len(articles)} articles...")
    for i, art in enumerate(articles, 1):
        image_path = art.get('final_image_path')
        if not image_path or not os.path.exists(image_path):
            continue
            
        slug = art.get('topic_slug', str(art['_id']))
        os.makedirs(os.path.join('output', 'ready_reels'), exist_ok=True)
        out_reel = os.path.abspath(os.path.join('output', 'ready_reels', f'{slug}.mp4'))
        
        if not os.path.exists(out_reel):
            headline = art.get('english_headline', 'Nepal Central News')
            print(f'  [{i}/{len(articles)}] Generating reel → {os.path.basename(out_reel)}')
            reel_path = generate_news_reel(image_path, headline, out_reel)
            art['final_reel_path'] = reel_path
        else:
            art['final_reel_path'] = out_reel


# ── Core 240-second slot processor ───────────────────────────────────────────
def process_article_slot(article, slot_index, total, db):
    """
    T + 0s   → Post image card to Facebook Feed
    T + 15s  → Post reel to Facebook Reels
    T + 15s → T + 240s → Sleep for remaining slot time
    Returns (success: bool, result_tag: str)
    """
    slot_start    = time.time()
    title_preview = article.get('original_title', 'Unknown')[:65]

    print(f'\n{"="*65}')
    print(f'[SLOT {slot_index}/{total}] {title_preview}')
    print(f'  Score: {article.get("priority_score", "?")} | '
          f'Source: {article.get("source_name", "?")}')
    print(f'{"="*65}')

    # ── Step 0: Ensure image file actually exists locally ────────
    image_path = article.get('final_image_path')
    if not image_path or not os.path.exists(image_path):
        print(f'  [!] Image missing locally (path: {image_path}). Reverting to text_scored to re-render.')
        try:
            db.articles.update_one(
                {'_id': article['_id']},
                {'$set': {'status': 'text_scored'}, '$unset': {'final_image_path': ''}}
            )
        except Exception:
            pass
        return False, 'missing_image'

    # ── Step 1: Post image card ─────────────────────────────────
    print('  [T+0s] Posting image card to Facebook Feed...')
    success, fb_id_or_err = post_to_facebook(article)

    reel_path = reel_id = None

    if not success:
        if 'pause' in str(fb_id_or_err).lower():
            print('  [!] Meta rate limit. Re-queuing article.')
            _mark_requeue(db, article)
            remaining = SLOT_DURATION - (time.time() - slot_start)
            if remaining > 0:
                time.sleep(remaining)
            return False, 'rate_limit'
        print(f'  [!] Image post failed: {fb_id_or_err}')
        _mark_failed(db, article, reason=str(fb_id_or_err))
        return False, 'image_fail'

    print(f'  [T+0s] ✓ Image card published. fb_post_id={fb_id_or_err}')

    # ── Step 2: Wait 15s then post reel (DISABLED) ─────────────
    # reel_wait = max(0, REEL_POST_DELAY - (time.time() - slot_start))
    # if reel_wait > 0:
    #     print(f'  [Waiting {reel_wait:.0f}s before reel...]')
    #     time.sleep(reel_wait)
    #
    # print(f'  [T+{int(time.time()-slot_start)}s] Posting pre-rendered reel to Facebook Reels...')
    # reel_path, reel_id = _post_pre_rendered_reel(article)
    reel_path = reel_id = None
    print('  [Reel] Generation and posting temporarily disabled.')

    # ── Step 3: Mark posted, delete local files immediately ────
    _mark_posted(db, article, fb_id_or_err, reel_id)

    # Instant cleanup — delete image card the moment they are posted
    image_path = article.get('final_image_path')
    _delete(image_path)
    # _delete(reel_path)

    # Clear the local path from DB so we don't accidentally retry a deleted file
    try:
        db.articles.update_one(
            {'_id': article['_id']},
            {'$unset': {'final_image_path': ''}}
        )
    except Exception as e:
        print(f'  [DB Error] Failed to unset image path: {e}')

    print('  [✓] Article fully processed (Image only).')

    # ── Step 4: Sleep for remainder of 240s slot ────────────────
    elapsed    = time.time() - slot_start
    log_feedback(article, fb_post_id=fb_id_or_err, reel_id=reel_id, processing_time_sec=elapsed)
    
    sleep_for  = SLOT_DURATION - elapsed
    if sleep_for > 0:
        print(f'  [TIMER] Sleeping {sleep_for:.1f}s until T+240s...')
        time.sleep(sleep_for)
    else:
        print('  [TIMER] Slot fully consumed. Moving immediately.')

    return True, fb_id_or_err


# ── Batch mode (GitHub Actions) ───────────────────────────────────────────────
def run_batch_schedule():
    """
    One full cycle:
      1. Scrape & score all sources (text only)
      2. Render images for TOP 15 only
      3. Post top-15 on 240s slots
    """
    print('\n' + '='*65)
    print('  NEPAL CENTRAL NEWS – BATCH MODE (GitHub Actions)')
    print('='*65)
    init_db()

    if os.environ.get('GITHUB_ACTIONS') == 'true':
        from database.db_client import get_db as _get_db
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        try:
            _db = _get_db()
            _hb = _db.telemetry.find_one({'device': 'laptop'})
            if _hb:
                _last = _hb['last_active']
                if _last.tzinfo is None:
                    _last = _last.replace(tzinfo=_tz.utc)
                _diff = (_dt.now(_tz.utc) - _last).total_seconds() / 60.0
                print(f'[GitHub] Laptop last heartbeat: {_diff:.1f} min ago.')
                if _diff < 5.0:
                    print('[GitHub] Laptop was active < 5 min ago. Skipping GitHub run.')
                    sys.exit(0)
                else:
                    print(f'[GitHub] Laptop inactive ({_diff:.1f} min). Proceeding with GitHub Actions run.')
        except Exception as _e:
            print(f'[GitHub] Heartbeat check failed ({_e}). Proceeding anyway.')

    # Phase 1: Scrape + score (text only)
    print('\n[Phase 1] Scraping & scoring all sources...')
    t0 = time.time()
    scrape_and_score_all()

    # Phase 2: Render images for top 15 only
    print('\n[Phase 2] Rendering images for top 15 articles...')
    render_images_for_top_n(TOP_N)
    t_scrape = time.time() - t0
    print(f'[Scraper] Total scrape+render time: {t_scrape/60:.1f} minutes')

    # Phase 3: Post top 15
    print('\n[Phase 3] Starting 4-minute dual-post schedule...')
    top_articles = get_top_15_queued()
    if not top_articles:
        print('[Phase 3] No articles ready. Exiting.')
        return
        
    # pre_render_reels(top_articles)  # DISABLED FOR NOW

    posted_count = 0
    for i, article in enumerate(top_articles, 1):
        db = get_db()  # refresh each slot so reconnect is picked up if DB dropped
        try:
            db.articles.update_one(
                {'_id': article['_id'], 'status': 'queued'},
                {'$set': {'status': 'processing', 'updated_at': datetime.now(timezone.utc)}}
            )
        except Exception as e:
            print(f'[DB Error] Could not mark processing: {e}')
            time.sleep(3)
            continue
        success, result = process_article_slot(article, i, len(top_articles), db)
        if result == 'rate_limit':
            print('[!] Rate limit hit. Waiting 5 min before next article.')
            time.sleep(300)
        if success:
            posted_count += 1

    print(f'\n[Done] Batch complete. Published {posted_count} news items.')


# ── Continuous local mode (laptop always-on) ──────────────────────────────────
def run_continuous_mode():
    """
    Adaptive continuous loop:
      - Measures how long Phase 1+2 take
      - Schedules next scrape so it finishes just before the queue empties
      - Heartbeat recorded every 60s so GitHub Actions can detect laptop is active
    """
    print('[Continuous] Nepal Central News automation (local mode).')
    print(f'[Continuous] Cycle: {TOP_N} articles × 4 min = 60 min per cycle.\n')
    init_db()

    while True:
        record_laptop_heartbeat()
        run_cleanup()

        cycle_start = time.time()
        print(f'\n[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] '
              f'Starting scrape+score cycle...')

        # ── Smart skip: if we already have 15+ queued articles, skip Phase 1 ──
        from database.db_client import get_db as _gdb
        _db = _gdb()
        _cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        _already_queued = _db.articles.count_documents(
            {'status': 'queued', 'created_at': {'$gte': _cutoff}})
        if _already_queued >= 15:
            print(f'[Phase 1] Skipping scrape — {_already_queued} articles already queued.')
            t_scrape = 0
        else:
            # ── Phase 1: Scrape & score ─────────────────────────────
            print('[Phase 1] Scraping & scoring all sources (text only)...')
            scrape_and_score_all()

        # ── Phase 2: Render top-15 images ──────────────────────
        print('[Phase 2] Rendering images for top 15 articles...')
        render_images_for_top_n(TOP_N)

        t_scrape = time.time() - cycle_start
        print(f'[Scraper] Took {t_scrape/60:.1f} min.')

        # ── Phase 3: Post top-15 on 240s slots ─────────────────
        top_articles = get_top_15_queued()
        db = get_db()

        if not top_articles:
            print('[Queue] No articles ready. Will re-scrape in 10 minutes.')
            for _ in range(10):
                record_laptop_heartbeat()
                time.sleep(60)
            continue
            
        # pre_render_reels(top_articles)  # DISABLED FOR NOW

        print(f'[Queue] {len(top_articles)} articles ready. '
              f'Starting 4-min slot schedule...\n')

        # Adaptive: schedule next scrape so it starts before queue runs dry
        # Total posting time = len(articles) × 240s
        # Next scrape should START at: (posting_window − t_scrape − buffer)
        posting_window = len(top_articles) * SLOT_DURATION
        next_scrape_in = max(0, posting_window - t_scrape - BUFFER_SECONDS)
        next_scrape_at = time.time() + next_scrape_in
        print(f'[Adaptive] Next scrape scheduled in {next_scrape_in/60:.1f} min '
              f'(T+{next_scrape_in:.0f}s from now).\n')

        for i, article in enumerate(top_articles, 1):
            record_laptop_heartbeat()

            try:
                db.articles.update_one(
                    {'_id': article['_id'], 'status': 'queued'},
                    {'$set': {'status': 'processing',
                              'updated_at': datetime.now(timezone.utc)}}
                )
            except Exception as e:
                print(f'[DB Error] Failed to update status to processing: {e}')
                time.sleep(5)
                continue
            success, result = process_article_slot(
                article, i, len(top_articles), db)

            if result == 'rate_limit':
                print('[!] Rate limit. Pausing remaining items until next cycle.')
                break

            # ── Trigger next scrape in the background at adaptive time ──
            if time.time() >= next_scrape_at and i < len(top_articles):
                print('\n[Adaptive] Background scrape triggered early...')
                scrape_and_score_all()
                render_images_for_top_n(TOP_N)
                
                # We do NOT pre_render_reels here because they will be fetched on the next cycle
                next_scrape_at = float('inf')   # don't trigger again this cycle

        print(f'\n[Cycle complete] Waiting for next scheduled scrape...')
        # Sleep until it's time for the next full cycle (if adaptive scrape wasn't triggered)
        sleep_remaining = next_scrape_at - time.time()
        if sleep_remaining > 3600:
            # Safety cap: never wait more than 1 hour between cycles
            print(f'[Safety] next_scrape_at was {sleep_remaining/60:.0f}min away — capping to 60min.')
            sleep_remaining = 3600
        while sleep_remaining > 0:
            record_laptop_heartbeat()
            time.sleep(min(60, sleep_remaining))
            sleep_remaining = next_scrape_at - time.time()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Nepal Central News Automated Publisher')
    parser.add_argument(
        '--batch-mode', action='store_true',
        help='Single scrape + Top-15 publish cycle then exit (GitHub Actions).')
    args = parser.parse_args()

    if args.batch_mode:
        run_batch_schedule()
    else:
        run_continuous_mode()
