# -*- coding: utf-8 -*-
import requests
import time
import os
import json
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

# ==========================================
# 🔑 APNI SARI KEYS (PRE-MAPPED & PATCHED)
# ==========================================
GEMINI_API_KEY = "AQ.Ab8RN6IIvJ3nZAT2ezXZUMh-auOJ8B2M3lCOYUlrVou6IOAtKg"
GROQ_API_KEY = "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"
OPENROUTER_API_KEY = "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"
# ==========================================

TARGET_SITES = [
    {"name": "Onlinekhabar", "category": "Business", "url": "https://www.onlinekhabar.com/content/business", "container_tag": "div", "container_class": "ok-news-card", "title_tag": "h2"},
    {"name": "Ekantipur", "category": "Politics", "url": "https://ekantipur.com/news", "container_tag": "article", "container_class": "normal", "title_tag": "h2"},
    {"name": "Ratopati", "category": "Koshi Province", "url": "https://ratopati.com/province/koshi", "container_tag": "div", "container_class": "item", "title_tag": "h3"},
    {"name": "Setopati", "category": "Social", "url": "https://setopati.com/social", "container_tag": "div", "container_class": "items", "title_tag": "span"}
]

HISTORY_FILE = "scraped_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f: return set(json.load(f))
        except: return set()
    return set()

def save_history(history_set):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(list(history_set)[-500:], f, ensure_ascii=False, indent=4)

def fetch_full_article_text(article_url):
    try:
        response = requests.get(article_url, headers=HEADERS, timeout=10, verify=False)
        if response.status_code != 200: return ""
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        full_text = []
        for p in paragraphs:
            txt = p.get_text(strip=True)
            if len(txt) > 40: full_text.append(txt)
        return "\n".join(full_text[:7])
    except:
        return ""

def generate_with_gemini(prompt):
    """API 1: Google Gemini (Patched to v1beta for Flash)"""
    if not GEMINI_API_KEY or "YOUR_" in GEMINI_API_KEY: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    try:
        res = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        if res.status_code == 200:
            return res.json()['contents'][0]['parts'][0]['text'].strip()
        else:
            print(f"      [X] Gemini API Error [Status {res.status_code}]: {res.text[:120]}")
    except Exception as e:
        print(f"      [X] Gemini Connection Failed: {str(e)}")
    return None

def generate_with_groq(prompt):
    """API 2: Groq Cloud (Switched to Gemma-2 to avoid 429 Rate Limits)"""
    if not GROQ_API_KEY or "YOUR_" in GROQ_API_KEY: return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",  # Updated to working active model
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content'].strip()
        else:
            print(f"      [X] Groq API Error [Status {res.status_code}]: {res.text[:120]}")
    except Exception as e:
        print(f"      [X] Groq Connection Failed: {str(e)}")
    return None

def generate_with_openrouter(prompt):
    """API 3: OpenRouter (Updated to currently active Free Model)"""
    if not OPENROUTER_API_KEY or "YOUR_" in OPENROUTER_API_KEY: return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "qwen/qwen-2.5-72b-instruct:free",  # Fully free and updated slug
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content'].strip()
        else:
            print(f"      [X] OpenRouter API Error [Status {res.status_code}]: {res.text[:120]}")
    except Exception as e:
        print(f"      [X] OpenRouter Connection Failed: {str(e)}")
    return None

def rewrite_to_template_rules(title, full_story):
    """3-Layer Fallback AI System"""
    prompt = f"""
    You are a professional news editor. Translate and rewrite the given Nepali news into a layout matching a strict visual graphic card template.
    
    STRICT TEMPLATE RULES:
    1. LANGUAGE: Translate the Nepali news into flawless English only. Do not use Nepali.
    2. HEADLINE: Catchy, punchy, Title Case, strictly between 6 to 9 words MAXIMUM.
    3. BODY TEXT: Core summary in EXACTLY ONE single sentence, strictly between 22 to 25 words MAXIMUM. No multiple sentences, no bullets.
    4. HIGHLIGHT KEYWORD: Exactly one critical keyword from the body text to color-code.
    5. FACTUALITY: Rely strictly on the scraped text. Do not hallucinate or add outside info.
    
    Original News Title: {title}
    Full Article Content: 
    ---
    {full_story}
    ---
    
    Output Format (Strictly return ONLY these 3 lines without markdown or asterisks):
    HEADLINE: [Insert headline here]
    BODY: [Insert single sentence here]
    HIGHLIGHT: [Insert the single keyword here]
    """
    
    # Try Gemini First
    output = generate_with_gemini(prompt)
    if output: return output
    
    # Try Groq Second
    print("    [Fallback] Switching to Groq API...")
    output = generate_with_groq(prompt)
    if output: return output
    
    # Try OpenRouter Third
    print("    [Fallback] Switching to OpenRouter API...")
    output = generate_with_openrouter(prompt)
    if output: return output
    
    return "HEADLINE: All AI Engines Failed\nBODY: Could not generate content because all 3 APIs returned an error.\nHIGHLIGHT: None"

def scrape_news():
    scraped_history = load_history()
    timestamp = time.strftime('%Y-%m-%d_%I-%M%p')
    output_filename = f"template_news_ready_{timestamp}.txt"
    
    max_articles_per_site = 2 
    total_new_news = 0
    
    print(f"[+] Multi-AI FailSafe System Active... Saving to: '{output_filename}'")
    
    with open(output_filename, "w", encoding="utf-8") as file:
        file.write("=========================================================================\n")
        file.write("             FAIL-SAFE MULTI-AI GRAPHIC TEMPLATE READY REPORT            \n")
        file.write(f"                     Generated on: {time.strftime('%Y-%m-%d %I:%M %p')}                 \n")
        file.write("=========================================================================\n\n")
        
        for site in TARGET_SITES:
            site_buffer = []
            articles_found = 0
            
            print(f" -> Checking {site['name']}...")
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
                    if title_text in scraped_history: continue
                    
                    link_elem = item.find('a', href=True) if hasattr(item, 'find') else None
                    if not link_elem and item.name == 'a': link_elem = item
                    if not link_elem: link_elem = item.find_next('a', href=True)
                    if not link_elem: continue
                    
                    full_link = urljoin(site['url'], link_elem['href'])
                        
                    articles_found += 1
                    total_new_news += 1
                    scraped_history.add(title_text)
                    
                    print(f"    [Deep Scrape] Fetching full article data...")
                    full_story_text = fetch_full_article_text(full_link)
                    if not full_story_text: full_story_text = title_text
                    
                    print(f"    [Smart AI Routing] Re-writing content...")
                    ai_ready_content = rewrite_to_template_rules(title_text, full_story_text)
                    
                    site_buffer.append(f"{ai_ready_content}\n")
                    site_buffer.append(f"SOURCE LINK: {full_link}\n")
                    site_buffer.append("-------------------------------------------------------------------------\n\n")
                    
                    time.sleep(2)
                
                if site_buffer:
                    file.write(f"SOURCE: {site['name'].upper()} ({site['category'].upper()})\n")
                    file.write("=========================================================================\n")
                    file.writelines(site_buffer)
                    file.write("\n")
                    
            except Exception as e:
                import traceback
                print(f"Error on {site['name']}: {e}")
                traceback.print_exc()
            time.sleep(1)
            
        if total_new_news == 0:
            file.write("\n No new articles found matching unique history filters.\n")
            print("\n[-] Everything is up to date.")
        else:
            print(f"\n[+] Done! Formatted {total_new_news} posts safely.")
            
    save_history(scraped_history)

if __name__ == "__main__":
    scrape_news()