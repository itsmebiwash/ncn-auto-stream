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

def generate_with_gemini(prompt):
    if not GEMINI_API_KEY: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    try:
        res = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        if res.status_code == 200:
            return res.json()['contents'][0]['parts'][0]['text'].strip()
    except Exception: pass
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
    1. HEADLINE: Journalistic, professional, Title Case, strictly 6 to 9 words MAXIMUM.
    2. BODY: Core summary in EXACTLY ONE single sentence, strictly 22 to 25 words MAXIMUM. No bullets, no multiple periods. Write like a serious news anchor.
    3. HIGHLIGHT: Exactly one critical keyword from the BODY text to color-code.
    4. CAPTION: A separate, highly professional news brief for Facebook, strictly between 40 to 50 words. NO EMOJIS. MUST read like an actual news report.
    5. IMAGE INTENT: If the news is about generic objects (bus, car, money, buildings, nature, abstract concepts), output 'PEXELS'. ONLY output 'ARTICLE' if the news focuses on a highly specific named person (e.g. a politician) or exact local event where a generic photo makes no sense.
    
    Original News Title: {title}
    Full Article Content: 
    ---
    {full_story}
    ---
    
    Output Format (Strictly return ONLY these 5 lines, or SKIP):
    HEADLINE: [Insert headline here]
    BODY: [Insert single sentence here]
    HIGHLIGHT: [Insert the single keyword here]
    CAPTION: [Insert 40-50 word caption here]
    IMAGE_INTENT: [ARTICLE or PEXELS]
    """
    
    output = generate_with_gemini(prompt)
    if output: return output
    output = generate_with_groq(prompt)
    if output: return output
    output = generate_with_openrouter(prompt)
    if output: return output
    
    return "HEADLINE: All AI Engines Failed\nBODY: Could not generate content because all 3 APIs returned an error.\nHIGHLIGHT: None\nCAPTION: We are currently experiencing technical difficulties processing the news content. Stay tuned for updates!\nIMAGE_INTENT: PEXELS"

def parse_ai_output(output):
    headline = "News Headline"
    body = "News body text goes here."
    highlight = ""
    caption = ""
    intent = "PEXELS"
    for line in output.split('\n'):
        if line.startswith('HEADLINE:'): headline = line.replace('HEADLINE:', '').strip()
        elif line.startswith('BODY:'): body = line.replace('BODY:', '').strip()
        elif line.startswith('HIGHLIGHT:'): highlight = line.replace('HIGHLIGHT:', '').strip()
        elif line.startswith('CAPTION:'): caption = line.replace('CAPTION:', '').strip()
        elif line.startswith('IMAGE_INTENT:'): intent = line.replace('IMAGE_INTENT:', '').strip().upper()
    return headline, body, highlight, caption, intent

def generate_html_card(headline, body, highlight, bg_image_url):
    if highlight and highlight.lower() != "none":
        pattern = re.compile(re.escape(highlight), re.IGNORECASE)
        body = pattern.sub(lambda m: f"<span class='highlight'>{m.group(0)}</span>", body)
        
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;500;700;800&family=Inter:wght@400;600&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                width: 1080px;
                height: 1350px;
                font-family: 'Poppins', sans-serif;
                background-image: url('{bg_image_url}');
                background-size: cover;
                background-position: center 20%;
                display: flex;
                flex-direction: column;
                justify-content: flex-end;
                color: #ffffff;
                position: relative;
                overflow: hidden;
            }}
            .overlay {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: linear-gradient(180deg, rgba(0, 30, 80, 0.1) 0%, rgba(0, 20, 60, 0.6) 40%, rgba(0, 10, 40, 0.95) 100%);
                z-index: 1;
            }}
            .logo-container {{
                position: absolute;
                top: 60px;
                left: 60px;
                z-index: 2;
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(15px);
                -webkit-backdrop-filter: blur(15px);
                padding: 15px 25px;
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
            }}
            .logo-container img {{
                height: 140px;
                width: auto;
            }}
            .content-wrapper {{
                position: relative;
                z-index: 2;
                margin: 0 60px 60px 60px;
                background: linear-gradient(135deg, rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0.05));
                backdrop-filter: blur(40px) saturate(180%);
                -webkit-backdrop-filter: blur(40px) saturate(180%);
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 40px;
                padding: 60px;
                box-shadow: 0 30px 60px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.5);
                display: flex;
                flex-direction: column;
                gap: 30px;
            }}
            .badge {{
                align-self: flex-start;
                background: linear-gradient(90deg, #FF3B30, #FF2D55);
                padding: 10px 20px;
                border-radius: 12px;
                font-size: 20px;
                font-weight: 800;
                letter-spacing: 2px;
                text-transform: uppercase;
                box-shadow: 0 4px 15px rgba(255, 59, 48, 0.4);
            }}
            .headline {{
                font-size: 65px;
                font-weight: 800;
                line-height: 1.15;
                letter-spacing: -1px;
                color: #ffffff;
                text-shadow: 0 4px 10px rgba(0,0,0,0.3);
            }}
            .body-text {{
                font-family: 'Inter', sans-serif;
                font-size: 32px;
                font-weight: 400;
                line-height: 1.6;
                color: #e2e8f0;
                max-width: 95%;
            }}
            .highlight {{
                color: #38bdf8;
                font-weight: 700;
                position: relative;
                white-space: nowrap;
                text-shadow: 0 0 10px rgba(56, 189, 248, 0.5);
            }}
            .highlight::after {{
                content: '';
                position: absolute;
                bottom: 2px;
                left: 0;
                width: 100%;
                height: 4px;
                background: #38bdf8;
                border-radius: 2px;
                opacity: 0.7;
            }}
        </style>
    </head>
    <body>
        <div class="overlay"></div>
        <div class="logo-container">
            <img src="file:///{LOGO_HTML_PATH}" alt="Logo">
        </div>
        <div class="content-wrapper">
            <div class="badge">NEWS ALERT</div>
            <div class="headline">{headline}</div>
            <div class="body-text">{body}</div>
        </div>
    </body>
    </html>
    """
    return html_content

def upload_to_facebook(image_path, caption):
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        print("    [!] FB Credentials missing. Skipping Facebook upload.")
        return False
        
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/photos"
    payload = {
        'message': caption,
        'access_token': FB_PAGE_ACCESS_TOKEN
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
        
    hti = Html2Image(size=(1080, 1350))
    hti.output_path = OUTPUT_DIR
    
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
