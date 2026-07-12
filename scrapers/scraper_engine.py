import json
import time
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

from scrapers.deduplicator import generate_hash, is_duplicate
from db.database import get_db
from ai.groq_processor import process_text_with_groq
from ai.gemini_vision import verify_image_with_gemini
from utils.image_utils import optimize_image, fetch_pexels_image
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

def process_single_article(source_name, title, url):
    content_hash = generate_hash(url, title)
    
    if is_duplicate(content_hash):
        print(f"[{source_name}] Duplicate dropped: {title}")
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
    groq_data = process_text_with_groq(title, url)
    if not groq_data:
        return

    if groq_data.get("is_duplicate_or_redundant") or groq_data.get("is_advertisement_or_promotional"):
        db.articles.update_one(
            {"content_hash": content_hash},
            {"$set": {"status": "filtered_out", "updated_at": datetime.now(timezone.utc)}}
        )
        return

    rel_score = groq_data.get("relevancy_score", 0)
    vir_score = groq_data.get("virality_potential_score", 0)
    priority_score = (rel_score * 0.6) + (vir_score * 0.4)
    topic_slug = groq_data.get("topic_slug", content_hash[:10])

    db.articles.update_one(
        {"content_hash": content_hash},
        {"$set": {
            "status": "text_processed",
            "english_headline": groq_data.get("english_headline"),
            "english_caption": groq_data.get("english_caption"),
            "english_description": groq_data.get("english_description"),
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
        vision_data = verify_image_with_gemini(image_url)
        is_faulty = vision_data.get("is_faulty_image", True)
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
        img_out = os.path.join("output", f"{topic_slug}.jpg")
        success, path_or_err = optimize_image(image_url, img_out)
        if success:
            final_image_path = path_or_err

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
