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
from facebook.trust_engine import TrustEngine
from ai.trend_analyzer import TrendAnalyzer
from utils.reel_generator import generate_news_reel
from utils.heartbeat import record_laptop_heartbeat, is_laptop_active
from utils.cleanup import run_cleanup
from utils.logger import log_feedback

# ── Constants ─────────────────────────────────────────────────────────────────
SLOT_DURATION   = 240    # 4 minutes per news item (image + reel + sleep)
REEL_POST_DELAY = 15     # seconds after image post before reel goes up
TOP_N           = 15     # articles per posting cycle
DEFAULT_TOP_N   = 15     # max articles per cycle (used by Trust Engine cap)
CYCLE_MINUTES   = 60     # total cycle window in minutes
BUFFER_SECONDS  = 300    # 5 min buffer before next scrape
FORCE_POST      = False  # Set True for emergency breaking-news override


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


def _mark_posted(db, article, fb_post_id, reel_id=None, posted_from='local'):
    try:
        db.articles.update_one(
            {'_id': article['_id']},
            {'$set': {
                'status':          'posted',
                'facebook_post_id': fb_post_id,
                'facebook_reel_id': reel_id,
                'posted_from':      posted_from,
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


def apply_trend_boosts():
    """
    Queries TrendAnalyzer for AI-detected trending topics (cached 24h),
    then adds +2.0 to the priority_score of matching queued/text_scored articles.
    This ensures trending content always rises to the top of the posting queue.
    """
    try:
        analyzer = TrendAnalyzer()
        trends = analyzer.analyze_current_trends()
        if not trends:
            return

        db = get_db()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        articles = list(db.articles.find({
            'status': {'$in': ['text_scored', 'queued']},
            'created_at': {'$gte': cutoff},
            'trend_boosted': {'$ne': True}
        }))

        boost_count = 0
        for art in articles:
            text = (
                str(art.get('original_title', '')) + ' ' +
                str(art.get('english_headline', '')) + ' ' +
                str(art.get('category', ''))
            ).lower()
            if any(t.lower() in text for t in trends):
                new_score = min(10.0, float(art.get('priority_score', 5.0)) + 2.0)
                db.articles.update_one(
                    {'_id': art['_id']},
                    {'$set': {'priority_score': new_score, 'trend_boosted': True}}
                )
                boost_count += 1

        if boost_count > 0:
            print(f'[Trend Engine] Boosted {boost_count} articles based on AI trends: {trends}')
    except Exception as e:
        print(f'[Trend Engine] Error applying boosts: {e}')


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
    # The DB may store either a bare filename OR a legacy absolute path.
    # Reconstruct the full local path at runtime so it works regardless
    # of which OS (Linux/GitHub vs Windows/Laptop) rendered the image.
    _project_root = os.path.dirname(os.path.abspath(__file__))
    _output_dir   = os.path.join(_project_root, 'output')
    raw_path = article.get('final_image_path', '')
    if raw_path and not os.path.isabs(raw_path):
        # Bare filename — reconstruct full local path
        image_path = os.path.join(_output_dir, raw_path)
    else:
        image_path = raw_path

    if not image_path or not os.path.exists(image_path):
        print(f'  [!] Image not found locally. Attempting on-demand re-render...')
        # Import here to avoid circular imports
        from scrapers.nepali_scraper import _render_single_article
        try:
            db.articles.update_one(
                {'_id': article['_id']},
                {'$set': {'status': 'text_scored'}, '$unset': {'final_image_path': ''}}
            )
            # Reload fresh article with updated status
            article = db.articles.find_one({'_id': article['_id']})
            if article and _render_single_article(article, index=slot_index):
                # Reload again with image path set
                article = db.articles.find_one({'_id': article['_id']})
                raw_path = article.get('final_image_path', '')
                if raw_path and not os.path.isabs(raw_path):
                    image_path = os.path.join(_output_dir, raw_path)
                else:
                    image_path = raw_path
                print(f'  [✓] On-demand render succeeded: {os.path.basename(image_path or "?")}')
            else:
                print(f'  [!] On-demand render also failed. Skipping article.')
                return False, 'missing_image'
        except Exception as re_err:
            print(f'  [!] Re-render exception: {re_err}. Skipping article.')
            return False, 'missing_image'

    # Patch the article dict so post_to_facebook sees the correct local path
    article['final_image_path'] = image_path

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
    is_github = os.environ.get('GITHUB_ACTIONS') == 'true'
    posted_source = 'github' if is_github else 'local'
    _mark_posted(db, article, fb_id_or_err, reel_id, posted_source)

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

    # ── Step 4: Sleep for remainder of 240s slot (LOCAL mode only) ────
    elapsed = time.time() - slot_start
    log_feedback(article, fb_post_id=fb_id_or_err, reel_id=reel_id, processing_time_sec=elapsed)

    # In GitHub Actions we skip the 4-min delay — the runner has only 28 min total.
    # On local continuous mode the sleep is handled by the calling loop, not here.
    is_github = os.environ.get('GITHUB_ACTIONS') == 'true'
    if not is_github:
        sleep_for = SLOT_DURATION - elapsed
        if sleep_for > 0:
            print(f'  [TIMER] Sleeping {sleep_for:.1f}s until T+240s...')
            time.sleep(sleep_for)
        else:
            print('  [TIMER] Slot fully consumed. Moving immediately.')
    else:
        print(f'  [TIMER] GitHub Actions mode – no slot delay. Moving to next article.')

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
        print('[GitHub] Laptop heartbeat check disabled. Proceeding with GitHub Actions run.')
        # from database.db_client import get_db as _get_db
        # from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        # try:
        #     _db = _get_db()
        #     _hb = _db.telemetry.find_one({'device': 'laptop'})
        #     if _hb:
        #         _last = _hb['last_active']
        #         if _last.tzinfo is None:
        #             _last = _last.replace(tzinfo=_tz.utc)
        #         _diff = (_dt.now(_tz.utc) - _last).total_seconds() / 60.0
        #         print(f'[GitHub] Laptop last heartbeat: {_diff:.1f} min ago.')
        #         if _diff < 5.0:
        #             print('[GitHub] Laptop was active < 5 min ago. Skipping GitHub run.')
        #             sys.exit(0)
    t0 = time.time()
    db = get_db()

    # ── CRITICAL FIX: Reset articles stuck in 'processing' from previous timed-out run ──
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    stuck_result = db.articles.update_many(
        {'status': 'processing', 'created_at': {'$gte': cutoff_24h}},
        {'$set': {'status': 'queued', 'updated_at': datetime.now(timezone.utc)}}
    )
    if stuck_result.modified_count > 0:
        print(f'[Startup] Reset {stuck_result.modified_count} stuck "processing" articles → "queued".')

    # ── Check how many articles are already queued & ready to post ──
    queued_count = db.articles.count_documents(
        {'status': 'queued', 'created_at': {'$gte': cutoff_24h}}
    )
    print(f'[Startup] {queued_count} articles currently queued and ready to post.')

    if queued_count >= 5:
        # Enough articles ready — skip straight to posting, save the time budget
        print('[Smart-Skip] 5+ articles queued. Skipping scrape to maximize posting time.')
    else:
        # Need fresh articles — run Phase 1 + 2
        print('\n[Phase 1] Scraping & scoring all sources...')
        scrape_and_score_all()

        print('\n[AI Curation] Applying trend boosts based on past engagement...')
        apply_trend_boosts()

        t_after_phase1 = time.time() - t0
        remaining_min = 28 - (t_after_phase1 / 60)
        print(f'[Phase 1] Done in {t_after_phase1/60:.1f} min. ~{remaining_min:.1f} min remaining.')

        # Only render if we have at least 8 minutes left (each image takes ~30s)
        if remaining_min >= 8:
            print('\n[Phase 2] Rendering images for top 15 articles...')
            render_images_for_top_n(DEFAULT_TOP_N)
            t_scrape = time.time() - t0
            print(f'[Scraper] Total scrape+render time: {t_scrape/60:.1f} minutes')
        else:
            print(f'[Phase 2] SKIPPED — only {remaining_min:.1f} min left, not enough for rendering.')

    # ── Phase 3: POST — Trust Engine controls volume ──────────────────────────
    elapsed_before_post = time.time() - t0
    print(f'\n[Phase 3] Starting posting. {28 - elapsed_before_post/60:.1f} min budget remaining.')

    # Determine page health and how many posts to publish this cycle
    trust_engine = TrustEngine()
    if FORCE_POST:
        state, cycle_limit, skip_links = 'EMERGENCY_OVERRIDE', DEFAULT_TOP_N, False
    else:
        state, cycle_limit, skip_links = trust_engine.evaluate_page_health()
    print(f'[Trust Engine] State={state} | Posts allowed={cycle_limit} | Skip links={skip_links}')

    top_articles = get_top_15_queued()
    if not top_articles:
        print('[Phase 3] No articles ready to post. Exiting.')
        return

    # Filter link-heavy posts when recovering/shadowbanned
    if skip_links:
        top_articles = [a for a in top_articles if 'http' not in str(a.get('original_content', ''))]

    approved_articles = top_articles[:cycle_limit]
    dropped_articles  = top_articles[cycle_limit:]

    # Archive excess articles — prevent queue clogging
    db = get_db()
    for drop in dropped_articles:
        try:
            db.articles.update_one(
                {'_id': drop['_id']},
                {'$set': {'status': 'archived_trust_drop', 'updated_at': datetime.now(timezone.utc)}}
            )
        except Exception:
            pass

    print(f'[Phase 3] {len(approved_articles)} approved (archived {len(dropped_articles)}).')

    # Spread posts evenly across remaining GitHub Actions budget (min 60s gap between posts)
    remaining_budget_sec = max(60, (25 * 60) - elapsed_before_post)
    dynamic_slot = max(60, remaining_budget_sec / max(1, len(approved_articles)))
    print(f'[Phase 3] Dynamic slot = {dynamic_slot:.0f}s per post to avoid spam.')

    posted_count = 0
    for i, article in enumerate(approved_articles, 1):
        elapsed = time.time() - t0
        if elapsed > 25 * 60:
            print(f'[GitHub] Approaching 28-min timeout. Stopping gracefully.')
            break

        db = get_db()
        try:
            db.articles.update_one(
                {'_id': article['_id'], 'status': 'queued'},
                {'$set': {'status': 'processing', 'updated_at': datetime.now(timezone.utc)}}
            )
        except Exception as e:
            print(f'[DB Error] Could not mark processing: {e}')
            time.sleep(3)
            continue

        slot_t = time.time()
        success, result = process_article_slot(article, i, len(approved_articles), db)
        if result == 'rate_limit':
            print('[!] Rate limit hit. Waiting 5 min before next article.')
            time.sleep(300)
        if success:
            posted_count += 1

        # Pace out posts — only sleep between posts, not after the last one
        if i < len(approved_articles):
            elapsed_slot = time.time() - slot_t
            sleep_for = max(0, dynamic_slot - elapsed_slot)
            if sleep_for > 0:
                print(f'  [Pacing] Sleeping {sleep_for:.0f}s before next post...')
                time.sleep(sleep_for)

    print(f'\n[Done] Batch complete. Published {posted_count} news items.')


# ── Continuous local mode (laptop always-on) ──────────────────────────────────
def run_continuous_mode():
    """
    Resilient continuous loop (local/laptop mode):
      - Trust Engine decides how many posts per cycle based on page health
      - AI Trend Analyzer boosts articles matching trending topics
      - Auto-restarts on any unhandled exception (60s cooldown)
      - Heartbeat recorded every slot so GitHub Actions detects laptop is active
    """
    print('[Continuous] Nepal Central News automation (local mode).')
    print(f'[Continuous] Trust Engine will set post volume per cycle (max {DEFAULT_TOP_N}).\n')
    init_db()

    while True:
        try:
            record_laptop_heartbeat()
            run_cleanup()

            cycle_start = time.time()
            print(f'\n[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Starting cycle...')

            # Smart skip: if 15+ articles queued already, skip scrape
            _db = get_db()
            _cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            _already_queued = _db.articles.count_documents(
                {'status': 'queued', 'created_at': {'$gte': _cutoff}})
            if _already_queued >= 15:
                print(f'[Phase 1] Skipping scrape — {_already_queued} articles already queued.')
            else:
                print('[Phase 1] Scraping & scoring all sources...')
                scrape_and_score_all()

                print('\n[AI Curation] Applying trend boosts...')
                apply_trend_boosts()

            # Phase 2: Render images
            print('[Phase 2] Rendering images for top articles...')
            render_images_for_top_n(DEFAULT_TOP_N)
            print(f'[Scraper] Took {(time.time()-cycle_start)/60:.1f} min.')

            # ── Phase 3: Trust Engine controls volume ─────────────────────────
            trust_engine = TrustEngine()
            if FORCE_POST:
                state, cycle_limit, skip_links = 'EMERGENCY_OVERRIDE', DEFAULT_TOP_N, False
            else:
                state, cycle_limit, skip_links = trust_engine.evaluate_page_health()
            print(f'[Trust Engine] State={state} | Posts allowed={cycle_limit} | Skip links={skip_links}')

            top_articles = get_top_15_queued()
            if not top_articles:
                print('[Queue] No articles ready. Re-scraping in 10 minutes.')
                for _ in range(10):
                    record_laptop_heartbeat()
                    time.sleep(60)
                continue

            # Filter links if recovering
            if skip_links:
                top_articles = [a for a in top_articles if 'http' not in str(a.get('original_content', ''))]

            approved_articles = top_articles[:cycle_limit]
            dropped_articles  = top_articles[cycle_limit:]

            db = get_db()
            for drop in dropped_articles:
                try:
                    db.articles.update_one(
                        {'_id': drop['_id']},
                        {'$set': {'status': 'archived_trust_drop', 'updated_at': datetime.now(timezone.utc)}}
                    )
                except Exception:
                    pass

            # Dynamic slot: fill remaining cycle time evenly (min 240s for local)
            elapsed_so_far = time.time() - cycle_start
            remaining_cycle = (CYCLE_MINUTES * 60) - elapsed_so_far
            dynamic_slot = max(240, remaining_cycle / max(1, len(approved_articles)))
            print(f'[Queue] {len(approved_articles)} articles approved (archived {len(dropped_articles)}). '
                  f'Slot duration: {dynamic_slot:.0f}s.\n')

            for i, article in enumerate(approved_articles, 1):
                record_laptop_heartbeat()
                db = get_db()

                try:
                    db.articles.update_one(
                        {'_id': article['_id'], 'status': 'queued'},
                        {'$set': {'status': 'processing', 'updated_at': datetime.now(timezone.utc)}}
                    )
                except Exception as e:
                    print(f'[DB Error] Failed to mark processing: {e}')
                    time.sleep(5)
                    continue

                slot_t = time.time()
                success, result = process_article_slot(article, i, len(approved_articles), db)

                if result == 'rate_limit':
                    print('[!] Rate limit. Pausing 5 min before next article.')
                    time.sleep(300)

                # Sleep for remaining dynamic slot (only between posts)
                if i < len(approved_articles):
                    elapsed_slot = time.time() - slot_t
                    sleep_for = max(0, dynamic_slot - elapsed_slot)
                    if sleep_for > 0:
                        print(f'  [Pacing] Sleeping {sleep_for:.0f}s before next post...')
                        time.sleep(sleep_for)

            print(f'\n[Cycle complete] Restarting cycle...')

        except KeyboardInterrupt:
            print('\n[Stopping] Keyboard interrupt. Exiting.')
            sys.exit(0)
        except Exception as e:
            print(f'\n[CRITICAL ERROR] Unhandled exception: {e}')
            print('[Recovery] Restarting in 60 seconds...')
            try:
                record_laptop_heartbeat()
            except Exception:
                pass
            time.sleep(60)


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

