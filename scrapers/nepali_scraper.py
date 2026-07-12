import json
import time
import os
import sys
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

def load_sources():
    sources_path = os.path.join(os.path.dirname(__file__), "..", "sources.json")
    try:
        with open(sources_path, "r") as f:
            return json.load(f).get("sources", [])
    except Exception as e:
        print(f"Error loading sources: {e}")
        return []

def extract_image_url(article_url):
    """Fallback simplistic image extractor."""
    try:
        resp = requests.get(article_url, timeout=10)
        soup = BeautifulSoup(resp.content, "html.parser")
        meta_og = soup.find("meta", property="og:image")
        if meta_og:
            return meta_og["content"]
    except:
        pass
    return None

def get_recent_titles(hours=9):
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    # We need a list of strings
    titles = []
    
    try:
        cursor = db.articles.execute(f"SELECT data FROM articles")
        rows = cursor.fetchall()
        for row in rows:
            data = json.loads(row[0])
            if "created_at" in data and "original_title" in data:
                # Basic string comparison for date fallback
                if data["created_at"] >= cutoff.isoformat():
                    titles.append(data["original_title"])
    except:
        # Fallback if using PyMongo directly
        try:
            results = db.articles.find({"created_at": {"$gte": cutoff}})
            for r in results:
                titles.append(r.get("original_title", ""))
        except:
            pass
    return titles

def is_cross_site_duplicate(new_title, recent_titles):
    # Jaccard Similarity of words as a fast local semantic check
    def get_tokens(text):
        if not text: return set()
        return set([w.lower() for w in text.split() if len(w) > 3])
        
    new_tokens = get_tokens(new_title)
    if not new_tokens: return False
    
    for old_title in recent_titles:
        old_tokens = get_tokens(old_title)
        if not old_tokens: continue
        
        intersection = len(new_tokens.intersection(old_tokens))
        union = len(new_tokens.union(old_tokens))
        
        if union == 0: continue
        
        score = intersection / union
        if score > 0.45: # High overlap means same core news event
            return True
            
    return False

def process_single_article(source_name, title, url):
    content_hash = generate_hash(url, title)
    
    if is_duplicate(content_hash):
        print(f"[{source_name}] Duplicate dropped (Hash match): {title}")
        return

    # Deep Cross-Site Deduplication Check
    recent_titles = get_recent_titles(hours=9)
    if is_cross_site_duplicate(title, recent_titles):
        print(f"[{source_name}] Duplicate dropped (Cross-site Semantic match): {title}")
        return

    db = get_db()
    now = datetime.now(timezone.utc)
    
    # Insert initial record
    db.articles.insert_one({
        "source_name": source_name,
        "original_url": url,
        "original_title": title,
        "content_hash": content_hash,
        "status": "scraped",
        "created_at": now,
        "updated_at": now
    })

    print(f"[{source_name}] Processing text: {title}")
    
    # 2. Text Processing (Groq)
    groq_data = process_text_with_groq(title, "")
    if not groq_data:
        return

    if groq_data.get("is_duplicate_story") or groq_data.get("is_advertisement_or_promo"):
        db.articles.update_one(
            {"content_hash": content_hash},
            {"$set": {"status": "filtered_out", "updated_at": datetime.now(timezone.utc)}}
        )
        return

    rel_score = groq_data.get("virality_score", 0)
    vir_score = groq_data.get("virality_score", 0)
    priority_score = vir_score
    topic_slug = content_hash[:10]

    db.articles.update_one(
        {"content_hash": content_hash},
        {"$set": {
            "status": "text_processed",
            "english_headline": groq_data.get("card_headline_nepali"),
            "english_caption": groq_data.get("card_subtitle_nepali"),
            "english_description": groq_data.get("fb_caption_text"),
            "hashtags": groq_data.get("hashtags", []),
            "pexels_search_keywords": groq_data.get("pexels_search_keywords", []),
            "topic_slug": topic_slug,
            "relevancy_score": rel_score,
            "virality_potential_score": vir_score,
            "priority_score": priority_score,
            "updated_at": datetime.now(timezone.utc)
        }}
    )

    # 3. Vision Processing
    image_url = extract_image_url(url)
    is_faulty = False
    
    if image_url:
        vision_data = verify_image_with_groq_vision(image_url)
        is_faulty = vision_data.get("is_faulty_or_ad_image", True)
    else:
        is_faulty = True

    final_image_path = None
    
    if is_faulty:
        print(f"[{source_name}] Image faulty or missing. Trying Pexels...")
        keywords = groq_data.get("pexels_search_keywords", [])
        fallback_url = fetch_pexels_image(keywords, PEXELS_API_KEY)
        if fallback_url:
            image_url = fallback_url

    if image_url:
        os.makedirs("output", exist_ok=True)
        bg_out = os.path.join("output", f"{topic_slug}_bg.jpg")
        success, bg_path = optimize_image(image_url, bg_out, target_size=(1080, 1350))
        
        if success:
            final_out = os.path.join("output", f"{topic_slug}.jpg")
            cat = "NEPAL CENTRAL NEWS"
            head = groq_data.get("card_headline_nepali", "")
            sub = groq_data.get("card_subtitle_nepali", "")
            
            rend_success, rend_path = render_html_card(bg_path, cat, head, sub, final_out)
            if rend_success:
                opt_success, path_or_err = optimize_image(rend_path, final_out, target_size=None)
                if opt_success:
                    final_image_path = path_or_err
                    try:
                        os.remove(bg_path)
                    except:
                        pass

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
    else:
        db.articles.update_one(
            {"content_hash": content_hash},
            {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc)}}
        )

def run_scraper_cycle():
    """Runs the scraper for all configured sources."""
    sources = load_sources()
    
    for source in sources:
        print(f"Scraping {source['name']}...")
        try:
            resp = requests.get(source['url'], timeout=10)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            links = soup.select(source.get('article_selector', 'a'))
            
            processed = 0
            for link in links:
                title = link.get_text(strip=True)
                url = link.get('href', '')
                if not url.startswith('http'):
                    url = source['url'] + url
                    
                if title and url and len(title) > 10:
                    process_single_article(source['name'], title, url)
                    processed += 1
                if processed >= 5:
                    break
        except Exception as e:
            print(f"Error scraping {source['name']}: {e}")
