"""
nepali_scraper.py

TWO-PHASE ARCHITECTURE:
  Phase 1 – scrape_and_score_all()
      Scrape all 48 sources, run Groq TEXT scoring only.
      Stores every article as status='text_scored'.
      NO image downloading at this stage.

  Phase 2 – render_images_for_top_n(n=15)
      Picks the top-N highest-priority articles that are still 'text_scored'.
      Downloads image / falls back to Pexels, renders HTML card.
      Updates status to 'queued'.

This means we never render more than 15 images per cycle.
"""
import json
import time
import os
import sys
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from scrapers.deduplicator import generate_hash, is_duplicate
from database.db_client import get_db
from ai.groq_manager import process_text_with_groq
from utils.image_utils import optimize_image, fetch_pexels_image
from utils.renderer import render_html_card
from config.settings import PEXELS_API_KEY

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_ARTICLES_PER_SOURCE = 8   # Max articles scraped per source per cycle
TOP_N_TO_RENDER         = 15  # Only render images for the top N priority articles

# ── Output post-processors ────────────────────────────────────────────────────
_SOURCE_PLACEHOLDER_PATTERNS = [
    r'\[स्रोतको नाम\]', r'\[source name\]', r'\[स्रोत\]',
    r'\[Source\]', r'\[source\]', r'\[URL\]', r'\[link\]',
    r'स्रोत:\s*\[.*?\]', r'Source:\s*\[.*?\]',
]

# Valid template categories (must match templates/*.html filenames)
_VALID_CATEGORIES = {
    'politics', 'crime', 'business', 'sports', 'health', 'technology',
    'education', 'entertainment', 'international', 'environment',
    'science', 'lifestyle', 'weather', 'opinion', 'general'
}

def _clean_caption(text: str) -> str:
    """Strip source placeholders and deduplicate repeated / paraphrased sentences."""
    if not text:
        return text

    # 1. Remove source placeholders
    for pat in _SOURCE_PLACEHOLDER_PATTERNS:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)

    # 2. Split into sentences (handles standard punctuation and run-on sentences without punctuation)
    # First, inject a special delimiter character \u200b after common verbs followed by spaces
    processed_text = text
    verbs = ['छ', 'छन्', 'थियो', 'थिए', 'भयो', 'भए', 'हो', 'हुन्', 'गरे', 'गरेका', 'गरेकी', 'गरेको']
    for verb in verbs:
        # Use regex boundary matching
        processed_text = re.sub(rf'\b{verb}\s+', f'{verb} \u200b', processed_text)

    # Now split on standard punctuation OR our special separator
    segments = re.split(r'([।\.\n\u200b]+)', processed_text)


    # 3. Deduplicate using both exact match AND Jaccard word-overlap
    def _tokens(s):
        # Nepali characters are Unicode, word characters include Devanagari.
        # Strip common stop-words or suffixes to compare roots.
        return set(w for w in re.sub(r'[^\w\s]', '', s).split() if len(w) > 1)

    def _is_similar(s, seen_tokens_list, threshold=0.35):
        st = _tokens(s)
        if not st:
            return False
        for ot in seen_tokens_list:
            if not ot:
                continue
            inter = len(st & ot)
            union = len(st | ot)
            if union and inter / union >= threshold:
                return True
        return False

    seen_exact  = set()
    seen_tokens_list = []
    deduped     = []

    for seg in segments:
        stripped = seg.strip()
        if not stripped:
            deduped.append(seg)
            continue
        key = re.sub(r'\s+', ' ', stripped.lower())
        if key in seen_exact or _is_similar(key, seen_tokens_list):
            continue   # drop this segment
        seen_exact.add(key)
        seen_tokens_list.append(_tokens(key))
        deduped.append(seg)

    result = ''.join(deduped).strip()
    result = result.replace('\u200b', '') # remove injected split markers
    return re.sub(r'\n{3,}', '\n\n', result)



def _clean_hashtags(hashtags: list) -> list:
    """Keep only ASCII hashtags — silently drops any Devanagari tags."""
    clean = []
    for tag in hashtags:
        tag = tag.strip()
        if not tag.startswith('#'):
            tag = '#' + tag
        if all(ord(c) < 128 for c in tag):
            clean.append(tag)
    return clean or ['#NepalCentralNews', '#Nepal', '#NCN']


def make_slug(text: str, max_len: int = 40) -> str:
    """Convert any text (Nepali or English) to an ASCII-safe filename slug."""
    ascii_text = text.encode('ascii', errors='ignore').decode('ascii')
    slug = re.sub(r'[^\w\s-]', '', ascii_text).strip().lower()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:max_len] if slug else 'news'


# ── Source loader ─────────────────────────────────────────────────────────────
def load_sources():
    path = os.path.join(os.path.dirname(__file__), '..', 'sources.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f).get('sources', [])
    except Exception as e:
        print(f'Error loading sources: {e}')
        return []


# ── Image helpers ─────────────────────────────────────────────────────────────
def _extract_og_image(article_url: str) -> str | None:
    """Try og:image from the article page. Returns URL or None."""
    try:
        resp = requests.get(article_url, timeout=10,
                            headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(resp.content, 'html.parser')
        meta = soup.find('meta', property='og:image')
        if meta and meta.get('content'):
            return meta['content']
        for img in soup.find_all('img', src=True):
            src = img['src']
            if src.startswith('http') and any(
                    ext in src for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                return src
    except Exception:
        pass
    return None


def _is_image_accessible(url: str) -> bool:
    """
    Lightweight HTTP HEAD check — replaces the decommissioned Groq vision model.
    Returns True if the URL responds with an image content-type.
    """
    try:
        resp = requests.head(url, timeout=6, allow_redirects=True,
                             headers={'User-Agent': 'Mozilla/5.0'})
        ct = resp.headers.get('Content-Type', '')
        return resp.status_code == 200 and 'image' in ct
    except Exception:
        return False


# ── Deduplication helpers ─────────────────────────────────────────────────────
def get_recent_titles(hours: int = 9) -> list:
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    titles = []
    try:
        for r in db.articles.find({'created_at': {'$gte': cutoff}}):
            titles.append(r.get('original_title', ''))
    except Exception:
        pass
    return titles


def is_cross_site_duplicate(new_title: str, recent_titles: list) -> bool:
    def tokens(t):
        return set(w.lower() for w in t.split() if len(w) > 3) if t else set()
    nt = tokens(new_title)
    if not nt:
        return False
    for old in recent_titles:
        ot = tokens(old)
        if not ot:
            continue
        if len(nt & ot) / len(nt | ot) > 0.45:
            return True
    return False


# ═════════════════════════════════════════════════════════════════════════════
# PHASE 1 – Scrape all sources, score with Groq TEXT only (NO image rendering)
# ═════════════════════════════════════════════════════════════════════════════
def _score_single_article(source_name: str, title: str, url: str, category: str,
                           recent_titles: list) -> None:
    """
    Deduplicates, calls Groq text model, stores article as 'text_scored'.
    Does NOT download images or render cards.
    """
    content_hash = generate_hash(url, title)
    if is_duplicate(content_hash):
        return
    if is_cross_site_duplicate(title, recent_titles):
        return

    db = get_db()
    now = datetime.now(timezone.utc)

    db.articles.insert_one({
        'source_name': source_name,
        'original_url': url,
        'original_title': title,
        'content_hash': content_hash,
        'category': category,
        'status': 'scraped',
        'created_at': now,
        'updated_at': now
    })

    groq_data = process_text_with_groq(title, '', category=category)
    if not groq_data:
        db.articles.update_one({'content_hash': content_hash},
                               {'$set': {'status': 'failed',
                                         'updated_at': datetime.now(timezone.utc)}})
        return

    if groq_data.get('is_advertisement_or_promo'):
        db.articles.update_one({'content_hash': content_hash},
                               {'$set': {'status': 'filtered_out',
                                         'updated_at': datetime.now(timezone.utc)}})
        return

    priority_score = float(groq_data.get('priority_score',
                                          groq_data.get('virality_score', 1.0)))

    # Use Groq-detected article category — NOT the source category.
    # e.g. a Crime article from Arthabeed (Business source) → 'Crime'
    raw_ai_category = groq_data.get('article_category', category).strip()
    # Validate against known template names; fall back to source category or General
    if raw_ai_category.lower() in _VALID_CATEGORIES:
        article_category = raw_ai_category.title()   # e.g. 'politics' → 'Politics'
    else:
        article_category = category if category.lower() in _VALID_CATEGORIES else 'General'

    head_for_slug = groq_data.get('card_headline_nepali', title)
    cat_slug  = make_slug(article_category)
    head_slug = make_slug(head_for_slug) or content_hash[:8]
    topic_slug = f'{cat_slug}_{head_slug}'

    caption_clean  = _clean_caption(groq_data.get('fb_caption_text', ''))
    hashtags_clean = _clean_hashtags(groq_data.get('hashtags', []))

    db.articles.update_one(
        {'content_hash': content_hash},
        {'$set': {
            'status':               'text_scored',
            'category':             article_category,   # overwrite with AI-detected category
            'english_headline':     groq_data.get('card_headline_nepali', ''),
            'english_caption':      groq_data.get('card_subtitle_nepali', ''),
            'english_description':  caption_clean,
            'hashtags':             hashtags_clean,
            'pexels_search_keywords': groq_data.get('pexels_search_keywords', []),
            'topic_slug':           topic_slug,
            'priority_score':       priority_score,
            'updated_at':           datetime.now(timezone.utc)
        }}
    )



def scrape_and_score_all() -> int:
    """
    Phase 1: Scrape all 48 sources and Groq-score every article (text only).
    Returns the number of newly scored articles.
    """
    sources = load_sources()
    print(f'[Phase 1] Scraping {len(sources)} sources (text scoring only)...')
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    # Pre-load recent titles once for cross-site dedup
    recent_titles = get_recent_titles(hours=9)
    scored = 0

    for source in sources:
        print(f'  Scraping {source["name"]} ...')
        try:
            resp = requests.get(source['url'], timeout=12, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')

            selector = source.get('article_selector', 'h2 a, h3 a')
            links = soup.select(selector)

            seen_titles = set()
            processed = 0
            for link in links:
                title = link.get_text(strip=True)
                href  = link.get('href', '')
                if not href.startswith('http'):
                    href = source['url'].rstrip('/') + '/' + href.lstrip('/')
                if not title or len(title) < 12 or title in seen_titles:
                    continue
                seen_titles.add(title)

                _score_single_article(
                    source['name'], title, href,
                    source.get('category', 'General'), recent_titles)
                recent_titles.append(title)   # update in-memory dedup list
                processed += 1
                scored += 1
                if processed >= MAX_ARTICLES_PER_SOURCE:
                    break

        except requests.exceptions.RequestException as e:
            print(f'  [!] Network error for {source["name"]}: {e}')
        except Exception as e:
            print(f'  [!] Error for {source["name"]}: {e}')

    print(f'[Phase 1] Done. {scored} articles scored.')
    return scored


# ═════════════════════════════════════════════════════════════════════════════
# PHASE 2 – Render images for TOP-N articles only
# ═════════════════════════════════════════════════════════════════════════════
def _render_single_article(article, index=1):
    """
    Downloads image, renders HTML card, updates DB.
    Updates DB status to 'queued' on success, 'failed' on failure.
    Returns True on success.
    """
    db = get_db()
    source_name = article.get('source_name', '?')
    content_hash = article['content_hash']
    url = article.get('original_url', '')
    category = article.get('category', 'General')

    # Step 1: Get og:image from article page
    image_url = _extract_og_image(url)
    use_pexels = True

    if image_url:
        # Quick HTTP check instead of decommissioned Groq vision model
        if _is_image_accessible(image_url):
            use_pexels = False
        else:
            image_url = None

    if use_pexels:
        keywords = article.get('pexels_search_keywords', [])
        fallback = fetch_pexels_image(keywords, PEXELS_API_KEY)
        if fallback:
            image_url = fallback

    if not image_url:
        print(f'  [{source_name}] ✗ No image found. Skipping.')
        db.articles.update_one({'content_hash': content_hash},
                               {'$set': {'status': 'failed',
                                         'updated_at': datetime.now(timezone.utc)}})
        return False

    # Step 2: Download + resize background
    output_dir = os.path.abspath('output')
    os.makedirs(output_dir, exist_ok=True)
    slug     = article.get('topic_slug', content_hash[:8])
    bg_out   = os.path.join(output_dir, f'{slug}_bg.jpg')
    final_out = os.path.join(output_dir, f'{slug}.jpg')
    ok, bg_path = False, bg_out
    if image_url:
        ok, bg_path = optimize_image(image_url, bg_out, target_size=(1080, 1350), check_dimensions=True)
        if not ok:
            print(f'  [{source_name}] ✗ Scraped image rejected/failed. Falling back to Pexels.')
            use_pexels = True

    if use_pexels:
        keywords = article.get('pexels_search_keywords', [])
        fallback = fetch_pexels_image(keywords, PEXELS_API_KEY)
        if fallback:
            ok, bg_path = optimize_image(fallback, bg_out, target_size=(1080, 1350), check_dimensions=False)
            image_url = fallback

    if not ok:
        print(f'  [{source_name}] ✗ Image download failed (both scraped and Pexels).')
        db.articles.update_one({'content_hash': content_hash},
                               {'$set': {'status': 'failed',
                                         'updated_at': datetime.now(timezone.utc)}})
        return False

    # Step 3: Render HTML card (1080x1350)
    head = article.get('english_headline', '')
    sub  = article.get('english_caption', '')
    rend_ok, rend_path = render_html_card(bg_path, category, head, sub, final_out, index=index)

    if not rend_ok:
        print(f'  [{source_name}] ✗ Card render failed.')
        try:
            os.remove(bg_path)
        except Exception:
            pass
        db.articles.update_one({'content_hash': content_hash},
                               {'$set': {'status': 'failed',
                                         'updated_at': datetime.now(timezone.utc)}})
        return False

    # Step 4: Final optimise
    opt_ok, final_path = optimize_image(rend_path, final_out, target_size=None)
    try:
        os.remove(bg_path)
    except Exception:
        pass

    if not opt_ok:
        final_path = rend_path   # use unoptimised render if optimise fails

    final_abs = os.path.abspath(final_path)
    db.articles.update_one(
        {'content_hash': content_hash},
        {'$set': {
            'status':            'queued',
            'original_image_url': image_url,
            'final_image_path':   final_abs,
            'updated_at':         datetime.now(timezone.utc)
        }}
    )
    print(f'  [{source_name}] ✓ Rendered → {os.path.basename(final_abs)}')
    return True


def render_images_for_top_n(n: int = TOP_N_TO_RENDER) -> int:
    """
    Phase 2: Pick top-N text_scored articles by priority and render their cards.
    Returns number successfully queued.
    """
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=3)

    top_articles = list(db.articles.find(
        {'status': 'text_scored', 'created_at': {'$gte': cutoff}},
        sort=[('priority_score', -1), ('created_at', -1)],
        limit=n
    ))

    if not top_articles:
        print(f'[Phase 2] No text_scored articles to render.')
        return 0

    print(f'[Phase 2] Rendering images for top {len(top_articles)} articles...')
    success_count = 0
    for i, art in enumerate(top_articles, 1):
        print(f'  [{i}/{len(top_articles)}] {art.get("original_title", "")[:65]}')
        if _render_single_article(art, index=i):
            success_count += 1

    print(f'[Phase 2] Done. {success_count}/{len(top_articles)} articles queued.')
    return success_count


# ── Legacy compatibility function (used by GitHub Actions batch mode) ─────────
def run_scraper_cycle():
    """Runs Phase 1 + Phase 2 sequentially (for backward compatibility)."""
    scrape_and_score_all()
    render_images_for_top_n(TOP_N_TO_RENDER)


# ── Top-15 queue fetcher (called by run_pipeline scheduler) ──────────────────
def get_top_15_queued() -> list:
    """Returns up to 15 highest-priority queued articles from the last 3 hours."""
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=3)
    try:
        return list(db.articles.find(
            {'status': 'queued', 'created_at': {'$gte': cutoff}},
            sort=[('priority_score', -1), ('created_at', -1)],
            limit=15
        ))
    except Exception as e:
        print(f'[DB] Error fetching top-15: {e}')
        return []
