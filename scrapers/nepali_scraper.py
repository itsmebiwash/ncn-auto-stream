import json
import time
import os
import sys
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# Ensure Nepali characters print correctly
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from scrapers.deduplicator import generate_hash, is_duplicate
from database.db_client import get_db
from ai.groq_manager import process_text_with_groq, verify_image_with_groq_vision
from utils.image_utils import optimize_image, fetch_pexels_image
from utils.renderer import render_html_card
from config.settings import PEXELS_API_KEY

# --- Scrape at most this many articles per source per cycle ---
MAX_ARTICLES_PER_SOURCE = 8

# ---------------------------------------------------------------
# Helper: load sources
# ---------------------------------------------------------------
def load_sources():
    sources_path = os.path.join(os.path.dirname(__file__), "..", "sources.json")
    try:
        with open(sources_path, "r", encoding="utf-8") as f:
            return json.load(f).get("sources", [])
    except Exception as e:
        print(f"Error loading sources: {e}")
        return []


# ---------------------------------------------------------------
# Helper: og:image extraction
# ---------------------------------------------------------------
def extract_image_url(article_url):
    """Try to get the og:image from an article page."""
    try:
        resp = requests.get(article_url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.content, "html.parser")
        meta_og = soup.find("meta", property="og:image")
        if meta_og and meta_og.get("content"):
            return meta_og["content"]
        # Fallback: first <img> with a src that looks like a real photo
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if src.startswith("http") and any(ext in src for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                return src
    except Exception:
        pass
    return None


# ---------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------
def get_recent_titles(hours=9):
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    titles = []
    try:
        results = db.articles.find({"created_at": {"$gte": cutoff}})
        for r in results:
            titles.append(r.get("original_title", ""))
    except Exception:
        pass
    return titles


def is_cross_site_duplicate(new_title, recent_titles):
    """Jaccard similarity check on word tokens."""
    def get_tokens(text):
        if not text:
            return set()
        return set(w.lower() for w in text.split() if len(w) > 3)

    new_tokens = get_tokens(new_title)
    if not new_tokens:
        return False

    for old_title in recent_titles:
        old_tokens = get_tokens(old_title)
        if not old_tokens:
            continue
        intersection = len(new_tokens & old_tokens)
        union = len(new_tokens | old_tokens)
        if union and intersection / union > 0.45:
            return True
    return False


# ---------------------------------------------------------------
# Slug generator (ASCII safe for filenames)
# ---------------------------------------------------------------
def make_slug(text, max_len=40):
    """Convert any text (Nepali or English) to a safe filename slug."""
    # Keep only ASCII alphanumeric and spaces/hyphens
    ascii_text = text.encode("ascii", errors="ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len] if slug else "news"


# ---------------------------------------------------------------
# Core: process a single article through the full pipeline
# ---------------------------------------------------------------
def process_single_article(source_name, title, url, category="General"):
    content_hash = generate_hash(url, title)

    if is_duplicate(content_hash):
        print(f"[{source_name}] Duplicate dropped (Hash match): {title[:60]}")
        return

    # Deep cross-site deduplication
    recent_titles = get_recent_titles(hours=9)
    if is_cross_site_duplicate(title, recent_titles):
        print(f"[{source_name}] Duplicate dropped (Semantic match): {title[:60]}")
        return

    db = get_db()
    now = datetime.now(timezone.utc)

    # ── Insert initial record ──────────────────────────────────
    db.articles.insert_one({
        "source_name": source_name,
        "original_url": url,
        "original_title": title,
        "content_hash": content_hash,
        "category": category,
        "status": "scraped",
        "created_at": now,
        "updated_at": now
    })

    print(f"[{source_name}] Processing: {title[:70]}")

    # ── Step 1: Groq text analysis ─────────────────────────────
    groq_data = process_text_with_groq(title, "", category=category)
    if not groq_data:
        db.articles.update_one(
            {"content_hash": content_hash},
            {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc)}}
        )
        return

    # Filter ads / promos
    if groq_data.get("is_advertisement_or_promo"):
        db.articles.update_one(
            {"content_hash": content_hash},
            {"$set": {"status": "filtered_out", "updated_at": datetime.now(timezone.utc)}}
        )
        return

    priority_score = float(groq_data.get("priority_score", groq_data.get("virality_score", 1.0)))

    # Build filename slug from headline
    headline_for_slug = groq_data.get("card_headline_nepali", title)
    cat_slug = make_slug(category)
    head_slug = make_slug(headline_for_slug)
    if not head_slug or head_slug == "news":
        head_slug = content_hash[:8]
    topic_slug = f"{cat_slug}_{head_slug}"

    db.articles.update_one(
        {"content_hash": content_hash},
        {"$set": {
            "status": "text_processed",
            "english_headline": groq_data.get("card_headline_nepali", ""),
            "english_caption": groq_data.get("card_subtitle_nepali", ""),
            "english_description": groq_data.get("fb_caption_text", ""),
            "hashtags": groq_data.get("hashtags", []),
            "pexels_search_keywords": groq_data.get("pexels_search_keywords", []),
            "topic_slug": topic_slug,
            "priority_score": priority_score,
            "updated_at": datetime.now(timezone.utc)
        }}
    )

    # ── Step 2: Image – try scraped og:image first, then Pexels ─
    image_url = extract_image_url(url)
    is_faulty = True

    if image_url:
        vision_data = verify_image_with_groq_vision(image_url)
        is_faulty = vision_data.get("is_faulty_or_ad_image", True)

    if is_faulty:
        print(f"  [{source_name}] Image faulty/missing – fetching Pexels...")
        keywords = groq_data.get("pexels_search_keywords", [])
        fallback_url = fetch_pexels_image(keywords, PEXELS_API_KEY)
        if fallback_url:
            image_url = fallback_url
            is_faulty = False

    final_image_path = None

    if image_url:
        os.makedirs("output", exist_ok=True)
        bg_out = os.path.join("output", f"{topic_slug}_bg.jpg")
        success, bg_path = optimize_image(image_url, bg_out, target_size=(1080, 1350))

        if success:
            final_out = os.path.join("output", f"{topic_slug}.jpg")
            head = groq_data.get("card_headline_nepali", "")
            sub  = groq_data.get("card_subtitle_nepali", "")

            rend_success, rend_path = render_html_card(bg_path, category, head, sub, final_out)
            if rend_success:
                opt_success, path_or_err = optimize_image(rend_path, final_out, target_size=None)
                if opt_success:
                    final_image_path = path_or_err
                    try:
                        os.remove(bg_path)
                    except Exception:
                        pass

    # ── Step 3: Update DB with final status ─────────────────────
    if final_image_path:
        db.articles.update_one(
            {"content_hash": content_hash},
            {"$set": {
                "status": "queued",
                "original_image_url": image_url,
                "is_faulty_image": is_faulty,
                "final_image_path": final_image_path,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        print(f"  [{source_name}] ✓ Queued: {topic_slug}")
    else:
        db.articles.update_one(
            {"content_hash": content_hash},
            {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc)}}
        )
        print(f"  [{source_name}] ✗ Failed to render image.")


# ---------------------------------------------------------------
# Scraper Cycle: scrape all 50 sources
# ---------------------------------------------------------------
def run_scraper_cycle():
    """Scrapes all configured sources for fresh articles."""
    sources = load_sources()
    print(f"[Scraper] Loaded {len(sources)} news sources.")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for source in sources:
        print(f"  Scraping {source['name']} ...")
        try:
            resp = requests.get(source["url"], timeout=12, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            selector = source.get("article_selector", "h2 a, h3 a")
            links = soup.select(selector)

            seen_titles = set()
            processed = 0

            for link in links:
                title = link.get_text(strip=True)
                href = link.get("href", "")

                # Normalise URL
                if not href.startswith("http"):
                    base = source["url"].rstrip("/")
                    href = base + "/" + href.lstrip("/")

                # Skip navigation / short strings / already seen in this batch
                if not title or len(title) < 12 or title in seen_titles:
                    continue
                seen_titles.add(title)

                category = source.get("category", "General")
                process_single_article(source["name"], title, href, category=category)
                processed += 1

                if processed >= MAX_ARTICLES_PER_SOURCE:
                    break

        except requests.exceptions.RequestException as e:
            print(f"  [!] Network error for {source['name']}: {e}")
        except Exception as e:
            print(f"  [!] Unexpected error for {source['name']}: {e}")


# ---------------------------------------------------------------
# Top-15 queue fetcher (called by the scheduler)
# ---------------------------------------------------------------
def get_top_15_queued():
    """Returns up to 15 highest-priority queued articles from the last 3 hours."""
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=3)
    try:
        articles = list(
            db.articles.find(
                {"status": "queued", "created_at": {"$gte": cutoff}},
                sort=[("priority_score", -1), ("created_at", -1)],
                limit=15
            )
        )
        return articles
    except Exception as e:
        print(f"[DB] Error fetching top-15: {e}")
        return []
