# -*- coding: utf-8 -*-
import requests
import time
import os
import json
import urllib3
import re
import shutil
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from html2image import Html2Image

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 🔑 ENVIRONMENT VARIABLES
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

TARGET_SITES = [
    {"name": "Onlinekhabar", "category": "Business", "url": "https://www.onlinekhabar.com/content/business", "container_tag": "div", "container_class": "ok-news-card", "title_tag": "h2"},
    {"name": "Ekantipur", "category": "Politics", "url": "https://ekantipur.com/news", "container_tag": "article", "container_class": "normal", "title_tag": "h2"},
    {"name": "Ratopati", "category": "Koshi Province", "url": "https://ratopati.com/province/koshi", "container_tag": "div", "container_class": "item", "title_tag": "h3"},
    {"name": "Setopati", "category": "Social", "url": "https://setopati.com/social", "container_tag": "div", "container_class": "items", "title_tag": "span"},
    {"name": "KhojSamachar", "category": "News", "url": "https://khojsamachar.com/", "container_tag": "article", "container_class": "post", "title_tag": "h2"},
    {"name": "JhapaNews", "category": "News", "url": "https://jhapanews.com/", "container_tag": "article", "container_class": "post", "title_tag": "h2"},
    {"name": "TimesOfIndia", "category": "World", "url": "https://timesofindia.indiatimes.com/world", "container_tag": "figure", "container_class": "", "title_tag": "figcaption"},
    {"name": "BBCNews", "category": "World", "url": "https://www.bbc.com/news/world", "container_tag": "div", "container_class": "sc-b8778340-3", "title_tag": "h2"}
]

HISTORY_FILE = "data/scraped_history.json"
OUTPUT_DIR = "output"
POSTED_DIR = os.path.join(OUTPUT_DIR, "posted")
ASSETS_DIR = "assets"
LOGO_PATH = os.path.abspath(os.path.join(ASSETS_DIR, "logo.png"))
LOGO_HTML_PATH = LOGO_PATH.replace('\\', '/')

def cleanup_old_files():
    """Auto deletes .txt and output .png files older than 48 hours in root/output."""
    now = time.time()
    cutoff = now - (48 * 3600)
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            filepath = os.path.join(OUTPUT_DIR, f)
            if os.path.isfile(filepath) and f.endswith('.png'):
                if os.path.getmtime(filepath) < cutoff:
                    try: os.remove(filepath)
                    except: pass
    for f in os.listdir('.'):
        if os.path.isfile(f) and f.endswith('.txt'):
            if os.path.getmtime(f) < cutoff:
                try: os.remove(f)
                except: pass

def is_similar_duplicate(new_title, history_set):
    """Cross-site semantic deduplication based on keyword overlap."""
    new_words = set(w for w in re.findall(r'\w+', new_title.lower()) if len(w) > 3)
    if not new_words: return False
    
    for old_title in history_set:
        old_words = set(w for w in re.findall(r'\w+', old_title.lower()) if len(w) > 3)
        if not old_words: continue
        
        intersection = new_words.intersection(old_words)
        # If there's 60% or more overlap in significant words (length > 3), consider it duplicate
        if len(intersection) / len(new_words) > 0.6:
            return True
    return False

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f: return set(json.load(f))
        except: return set()
    return set()

def save_history(history_set):
    if not os.path.exists("data"):
        os.makedirs("data")
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(list(history_set)[-1000:], f, ensure_ascii=False, indent=4)

def fetch_full_article_text_and_image(article_url):
    try:
        response = requests.get(article_url, headers=HEADERS, timeout=15, verify=False)
        if response.status_code != 200: return "", None
        soup = BeautifulSoup(response.text, 'html.parser')
        
        paragraphs = soup.find_all('p')
        full_text = []
        for p in paragraphs:
            txt = p.get_text(strip=True)
            if len(txt) > 40: full_text.append(txt)
        text_content = "\n".join(full_text[:7])
        
        img_url = None
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            img_url = og_image['content']
        if not img_url:
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter_image and twitter_image.get('content'):
                img_url = twitter_image['content']
                
        if img_url:
            reject_keywords = ['logo', 'default', 'placeholder', 'favicon']
            if any(keyword in img_url.lower() for keyword in reject_keywords):
                img_url = None
                
        return text_content, img_url
    except Exception as e:
        return "", None

def get_pexels_image(keyword):
    if not PEXELS_API_KEY or not keyword or keyword.lower() == "none":
        return None
    url = f"https://api.pexels.com/v1/search?query={keyword}&per_page=1"
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get('photos'):
                return data['photos'][0]['src']['large2x']
    except Exception:
        pass
    return None

# Handle multiple Gemini Keys (API Rotation)
GEMINI_API_KEYS_RAW = os.environ.get("GEMINI_API_KEYS", "")
GEMINI_API_KEYS = [k.strip() for k in GEMINI_API_KEYS_RAW.split(",") if k.strip()]

def generate_with_gemini(prompt):
    if not GEMINI_API_KEYS: return None
    
    for key in GEMINI_API_KEYS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        try:
            res = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
            if res.status_code == 200:
                return res.json()['contents'][0]['parts'][0]['text'].strip()
            else:
                print(f"    [Gemini] Key {key[:6]}... returned {res.status_code}. Trying next key...")
        except Exception:
            pass
            
    return None

def generate_with_groq(prompt):
    if not GROQ_API_KEY: return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200: return res.json()['choices'][0]['message']['content'].strip()
    except Exception: pass
    return None

def generate_with_openrouter(prompt):
    if not OPENROUTER_API_KEY: return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "qwen/qwen-2.5-72b-instruct:free", "messages": [{"role": "user", "content": prompt}]}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200: return res.json()['choices'][0]['message']['content'].strip()
    except Exception: pass
    return None

def rewrite_to_template_rules(title, full_story):
    prompt = f"""
    You are an expert, professional News Journalist. Read the following scraped text and generate 5 specific text elements.
    If the text is gibberish, nonsensical (e.g., 'drone war torn thread' with no context), or not a real news article, output exactly: SKIP
    
    STRICT RULES:
    1. RED_BOX_1: A short, punchy, high-impact phrase summarizing the core subject (Strictly 4-7 words).
    2. RED_BOX_2: A secondary punchy phrase complementing the first (Strictly 2-5 words). Example: 'During National Crises'.
    3. HEADLINE: The full, detailed headline summarizing the news clearly and professionally (10-25 words).
    4. CAPTION: A comprehensive, highly professional news report for Facebook, consisting of 3 to 4 detailed paragraphs (approx 150-200 words). NO EMOJIS. MUST read like a high-quality journalistic article.
    5. IMAGE INTENT: If the news is about generic objects (bus, car, money, buildings, nature, abstract concepts), output 'PEXELS'. ONLY output 'ARTICLE' if the news focuses on a highly specific named person (e.g. a politician) or exact local event where a generic photo makes no sense.
    
    Original News Title: {title}
    Full Article Content: 
    ---
    {full_story}
    ---
    
    Output Format (Strictly return ONLY these 5 lines, or SKIP):
    RED_BOX_1: [Insert short phrase here]
    RED_BOX_2: [Insert very short phrase here]
    HEADLINE: [Insert full headline here]
    CAPTION: [Insert 150-200 word caption here]
    IMAGE_INTENT: [ARTICLE or PEXELS]
    """
    
    output = generate_with_groq(prompt)
    if output: return output
    output = generate_with_openrouter(prompt)
    if output: return output
    output = generate_with_gemini(prompt)
    if output: return output
    
    return "RED_BOX_1: All AI Engines Failed\nRED_BOX_2: API Error\nHEADLINE: Could not generate content because all 3 APIs returned an error.\nCAPTION: We are currently experiencing technical difficulties processing the news content. Stay tuned for updates!\nIMAGE_INTENT: PEXELS"

def parse_ai_output(output):
    box1 = "BREAKING NEWS"
    box2 = "UPDATE"
    headline = "News Headline"
    caption = "News body text goes here."
    intent = "PEXELS"
    for line in output.split('\n'):
        if line.startswith('RED_BOX_1:'): box1 = line.replace('RED_BOX_1:', '').strip()
        elif line.startswith('RED_BOX_2:'): box2 = line.replace('RED_BOX_2:', '').strip()
        elif line.startswith('HEADLINE:'): headline = line.replace('HEADLINE:', '').strip()
        elif line.startswith('CAPTION:'): caption = line.replace('CAPTION:', '').strip()
        elif line.startswith('IMAGE_INTENT:'): intent = line.replace('IMAGE_INTENT:', '').strip().upper()
    return headline, box1, box2, caption, intent

def generate_html_card(headline, box1, box2, bg_image_url):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@400;600;800&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                width: 1080px;
                height: 1350px;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background-image: url('{bg_image_url}');
                background-size: cover;
                background-position: center;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                position: relative;
                overflow: hidden;
            }}
            /* Subtle dark vignette to make text pop */
            .vignette {{
                position: absolute;
                top: 0; left: 0; right: 0; bottom: 0;
                background: radial-gradient(circle at center, transparent 30%, rgba(0,0,0,0.4) 100%);
                z-index: 1;
            }}
            .logo-wrapper {{
                position: relative;
                z-index: 10;
                margin: 40px;
                align-self: flex-start;
                background: rgba(0, 0, 0, 0.2);
                backdrop-filter: blur(15px) saturate(120%);
                -webkit-backdrop-filter: blur(15px) saturate(120%);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 20px;
                padding: 12px 20px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.2);
            }}
            .logo-wrapper img {{
                height: 70px;
                width: auto;
            }}
            /* The main Liquid Glass Container */
            .liquid-glass-card {{
                position: relative;
                z-index: 10;
                margin: 40px;
                margin-top: auto;
                background: rgba(25, 25, 30, 0.65); /* Darker translucent for dramatic iOS contrast */
                backdrop-filter: blur(35px) saturate(200%);
                -webkit-backdrop-filter: blur(35px) saturate(200%);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-top: 1px solid rgba(255, 255, 255, 0.4); /* Top highlight */
                border-radius: 40px;
                padding: 60px 50px 40px 50px;
                box-shadow: 0 30px 60px rgba(0,0,0,0.5), inset 0 2px 2px rgba(255,255,255,0.1);
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
            }}
            /* Floating vibrant capsules (replacing red boxes) */
            .capsule-group {{
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                justify-content: center;
                margin-bottom: 30px;
            }}
            .capsule {{
                background: rgba(255, 59, 48, 0.9); /* Apple Red */
                color: #fff;
                font-size: 22px;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                padding: 12px 28px;
                border-radius: 100px; /* Pill shape */
                box-shadow: 0 8px 25px rgba(255, 59, 48, 0.5), inset 0 2px 5px rgba(255,255,255,0.3);
                border: 1px solid rgba(255, 255, 255, 0.3);
            }}
            .capsule-secondary {{
                background: rgba(0, 122, 255, 0.9); /* Apple Blue */
                box-shadow: 0 8px 25px rgba(0, 122, 255, 0.5), inset 0 2px 5px rgba(255,255,255,0.3);
            }}
            .headline {{
                font-size: 48px;
                font-weight: 800;
                line-height: 1.35;
                color: #ffffff;
                margin-bottom: 40px;
                letter-spacing: -0.5px;
                text-shadow: 0 2px 10px rgba(0,0,0,0.2);
            }}
            .footer-divider {{
                width: 100%;
                height: 1px;
                background: linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.3) 50%, rgba(255,255,255,0) 100%);
                margin-bottom: 25px;
            }}
            .footer {{
                font-size: 22px;
                font-weight: 800;
                color: rgba(255,255,255,0.7);
                letter-spacing: 4px;
                text-transform: uppercase;
            }}
            .footer span {{
                color: #ff3b30; /* Highlighted text */
            }}
        </style>
    </head>
    <body>
        <div class="vignette"></div>
        <div class="logo-wrapper">
            <img src="file:///{LOGO_HTML_PATH}" alt="Logo">
        </div>
        
        <div class="liquid-glass-card">
            <div class="capsule-group">
                <div class="capsule">{box1}</div>
                <div class="capsule capsule-secondary">{box2}</div>
            </div>
            <div class="headline">{headline}</div>
            <div class="footer-divider"></div>
            <div class="footer">NEPAL CENTRAL <span>NEWS</span></div>
        </div>
    </body>
    </html>
    """
    return html_content

def get_page_access_token():
    """Exchange User Access Token for Page Access Token."""
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        return None
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}"
    params = {
        "fields": "access_token",
        "access_token": FB_PAGE_ACCESS_TOKEN
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        if "access_token" in data:
            print(f"    [Facebook] Page Access Token fetched successfully!")
            return data["access_token"]
        else:
            print(f"    [Facebook Token Error] {data}")
            return None
    except Exception as e:
        print(f"    [Facebook Token Exception] {str(e)}")
        return None

def upload_to_facebook(image_path, caption):
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        print("    [!] FB Credentials missing. Skipping Facebook upload.")
        return False

    page_token = get_page_access_token()
    if not page_token:
        print("    [!] Could not get Page Access Token. Skipping upload.")
        return False
        
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/photos"
    payload = {
        'message': caption,
        'access_token': page_token
    }
    
    try:
        with open(image_path, 'rb') as f:
            files = {'source': f}
            response = requests.post(url, data=payload, files=files, timeout=30)
            
        if response.status_code == 200:
            print(f"    [Facebook] Successfully posted to Page ID {FB_PAGE_ID}!")
            return True
        else:
            print(f"    [Facebook Error] {response.text}")
            return False
    except Exception as e:
        print(f"    [Facebook Exception] {str(e)}")
        return False

def scrape_news():
    cleanup_old_files()
    scraped_history = load_history()
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    if not os.path.exists(POSTED_DIR):
        os.makedirs(POSTED_DIR)
    hti = Html2Image(size=(1080, 1350), browser_executable='google-chrome')
    hti.output_path = OUTPUT_DIR
    hti.browser.flags = ['--no-sandbox', '--disable-setuid-sandbox', '--allow-file-access-from-files']
    max_articles_per_site = 5
    
    print(f"[+] Automated Facebook DevOps Scraper Started...")
    
    ready_to_post = []
    
    for site in TARGET_SITES:
        articles_found = 0
        print(f" -> [Scraping] Checking {site['name']}...")
        try:
            response = requests.get(site['url'], headers=HEADERS, timeout=15, verify=False)
            if response.status_code != 200: continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            containers = soup.find_all(site['container_tag'], class_=site['container_class'])
            if not containers:
                containers = soup.find_all(['h2', 'h3', 'article'])
            
            for item in containers:
                if articles_found >= max_articles_per_site: break
                
                if item.name in ['h2', 'h3']:
                    title_text = item.get_text(strip=True)
                else:
                    title_elem = item.find(site['title_tag']) or item.find(['h1', 'h2', 'h3', 'a'])
                    title_text = title_elem.get_text(strip=True) if title_elem else ""
                
                if not title_text or len(title_text) < 15: continue
                if title_text in scraped_history or is_similar_duplicate(title_text, scraped_history):
                    print(f"    [Skip] Duplicate or highly similar news found: {title_text[:30]}...")
                    continue
                
                # Filter out generic/non-news items
                reject_titles = ["team", "about us", "contact", "privacy policy", "terms", "subscribe", "our team", "advertise", "home", "news"]
                if any(rej in title_text.lower() for rej in reject_titles) or len(title_text.split()) < 4: 
                    continue
                
                link_elem = item.find('a', href=True) if hasattr(item, 'find') else None
                if not link_elem and item.name == 'a': link_elem = item
                if not link_elem: link_elem = item.find_next('a', href=True)
                if not link_elem: continue
                
                full_link = urljoin(site['url'], link_elem['href'])
                
                print(f"    [Deep Scrape] Fetching full article & image...")
                full_story_text, bg_img = fetch_full_article_text_and_image(full_link)
                if not full_story_text: full_story_text = title_text
                
                print(f"    [AI Rewriting] Processing context & translating...")
                ai_ready_content = rewrite_to_template_rules(title_text, full_story_text)
                
                if ai_ready_content.strip() == "SKIP":
                    print(f"    [AI Skip] AI determined this is gibberish or non-news: {title_text[:30]}...")
                    continue
                    
                headline, body, highlight, caption, intent = parse_ai_output(ai_ready_content)
                
                if "All AI Engines Failed" in headline:
                    print("    [!] All AI engines failed. Skipping graphic generation.")
                    continue
                    
                articles_found += 1
                scraped_history.add(title_text)
                        
                print(f"    [Image Sourcing] Intent: {intent}")
                bg_img_final = None
                
                if intent == "PEXELS":
                    print("    [Image Sourcing] Attempting Pexels API...")
                    bg_img_final = get_pexels_image(highlight)
                    if not bg_img_final and bg_img:
                        print("    [Image Sourcing] Pexels failed. Falling back to Article Image.")
                        bg_img_final = bg_img
                else: # ARTICLE intent
                    print("    [Image Sourcing] Attempting Article Image...")
                    bg_img_final = bg_img
                    if not bg_img_final:
                        print("    [Image Sourcing] Article image missing. Falling back to Pexels...")
                        bg_img_final = get_pexels_image(highlight)
                        
                if not bg_img_final:
                    bg_img_final = "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=1080&h=1350&fit=crop"
                
                print("    [HTML Canvas Rendered] Compiling layout...")
                html_code = generate_html_card(headline, body, highlight, bg_img_final)
                
                safe_headline = re.sub(r'[^a-zA-Z0-9]', '_', headline)
                safe_headline = re.sub(r'_+', '_', safe_headline).strip('_')
                if len(safe_headline) > 50: safe_headline = safe_headline[:50]
                
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                filename = f"{safe_headline}_{timestamp}.png"
                img_path = os.path.join(OUTPUT_DIR, filename)
                
                print(f"    [PNG Generated] Saving to output/{filename}...")
                hti.screenshot(html_str=html_code, save_as=filename)
                
                ready_to_post.append((img_path, caption, filename))
                
        except Exception as e:
            print(f"    [ERROR] Exception on {site['name']}: {e}")
        time.sleep(1)
        
    if not ready_to_post:
        print("\n[-] No new articles found or generated. Everything is up to date.")
    else:
        print(f"\n[+] Generation complete! Found {len(ready_to_post)} images. Entering global 20-minute upload window...")
        
        # We want to randomly upload all images within a 20-minute (1200 seconds) window.
        # Max average wait between posts to fit in 20 minutes:
        max_total_wait = 1200
        avg_wait = max(30, max_total_wait // len(ready_to_post))
        
        for i, (img_path, caption, filename) in enumerate(ready_to_post):
            success = upload_to_facebook(img_path, caption)
            if success:
                print(f"    [Archive] Moving {filename} to posted/ folder...")
                archive_path = os.path.join(POSTED_DIR, filename)
                shutil.move(img_path, archive_path)
            
            if i < len(ready_to_post) - 1:
                # Calculate a random delay that keeps us on track for the 20 minute window
                delay_seconds = random.randint(30, avg_wait * 2)
                delay_minutes = delay_seconds / 60.0
                print(f"    [Global Anti-Spam] Sleeping for {delay_minutes:.1f} minutes before the next post in the queue...")
                time.sleep(delay_seconds)
            else:
                time.sleep(2)
                
        print(f"\n[+] Pipeline Completed! {len(ready_to_post)} articles processed and uploaded.")
        
    save_history(scraped_history)

if __name__ == "__main__":
    scrape_news()
