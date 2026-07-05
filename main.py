# -*- coding: utf-8 -*-
"""
=============================================================================
  NEPAL CENTRAL NEWS — Multi-Content Automation Engine
  Modes (by Nepal Standard Time hour):
    MODE 1 (News)        : 6 AM - 9 AM  | Default fallback
    MODE 2 (Gold/Silver) : 10 AM - 12 PM
    MODE 3 (On This Day) : 1 PM - 4 PM
    MODE 4 (Pop Culture) : 5 PM - 8 PM
    MODE 5 (NASA APOD)   : 9 PM+
=============================================================================
"""
import requests, time, os, json, urllib3, re, shutil, random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from html2image import Html2Image
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================
GEMINI_API_KEY       = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY         = os.environ.get("GROQ_API_KEY")
OPENROUTER_API_KEY   = os.environ.get("OPENROUTER_API_KEY")
FB_PAGE_ID           = os.environ.get("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN")
PEXELS_API_KEY       = os.environ.get("PEXELS_API_KEY")
NASA_API_KEY         = "4ZKne2vBHpJjmw1qPTWTPRPjsGr1syAdP1sTsNC3"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# ============================================================
# API KEY ROTATION
# ============================================================
GROQ_API_KEYS_RAW  = os.environ.get("GROQ_API_KEYS", "")
GROQ_API_KEYS      = [k.strip() for k in GROQ_API_KEYS_RAW.split(",") if k.strip()]
if not GROQ_API_KEYS and GROQ_API_KEY:
    GROQ_API_KEYS = [GROQ_API_KEY]

GEMINI_API_KEYS_RAW = os.environ.get("GEMINI_API_KEYS", "")
GEMINI_API_KEYS     = [k.strip() for k in GEMINI_API_KEYS_RAW.split(",") if k.strip()]
if not GEMINI_API_KEYS and GEMINI_API_KEY:
    GEMINI_API_KEYS = [GEMINI_API_KEY]

# ============================================================
# PATHS & CONSTANTS
# ============================================================
HISTORY_FILE = "data/scraped_history.json"
OUTPUT_DIR   = "output"
POSTED_DIR   = os.path.join(OUTPUT_DIR, "posted")
ASSETS_DIR   = "assets"
LOGO_PATH    = os.path.abspath(os.path.join(ASSETS_DIR, "logo.png"))
LOGO_HTML    = LOGO_PATH.replace('\\', '/')
FLAGS_DIR    = os.path.join(os.path.abspath(ASSETS_DIR), "Flag PNG")

NEPAL_TZ     = timedelta(hours=5, minutes=45)

# Country name → ISO 3166-1 alpha-2 code for PNG flag lookup
COUNTRY_CODE_MAP = {
    "Argentina":"ar","Brazil":"br","France":"fr","Germany":"de","Spain":"es",
    "England":"gb-eng","Portugal":"pt","Netherlands":"nl","Belgium":"be","Italy":"it",
    "Croatia":"hr","Uruguay":"uy","Mexico":"mx","United States":"us","Canada":"ca",
    "Morocco":"ma","Senegal":"sn","Japan":"jp","South Korea":"kr","Australia":"au",
    "Saudi Arabia":"sa","Iran":"ir","Switzerland":"ch","Denmark":"dk","Poland":"pl",
    "Serbia":"rs","Ukraine":"ua","Colombia":"co","Ecuador":"ec","Peru":"pe",
    "Chile":"cl","Venezuela":"ve","Egypt":"eg","Nigeria":"ng","Cameroon":"cm",
    "Ghana":"gh","Norway":"no","Sweden":"se","Turkey":"tr","Austria":"at",
    "Czech Republic":"cz","Hungary":"hu","Slovakia":"sk","Romania":"ro",
    "Scotland":"gb-sct","Wales":"gb-wls","Ireland":"ie","Greece":"gr","Algeria":"dz",
    "Tunisia":"tn","Mali":"ml","Ivory Coast":"ci","New Zealand":"nz","Qatar":"qa",
    "Indonesia":"id","Cuba":"cu","Bolivia":"bo","Panama":"pa","Honduras":"hn",
    "Costa Rica":"cr","El Salvador":"sv","Guatemala":"gt","Jamaica":"jm",
    "Paraguay":"py","Nepal":"np","India":"in","Pakistan":"pk","Sri Lanka":"lk",
    "China":"cn","Russia":"ru","United Arab Emirates":"ae","Kenya":"ke",
}

def get_flag_path(country_name):
    """Return absolute file:// path to flag PNG, or None if not found."""
    code = COUNTRY_CODE_MAP.get(country_name, "").lower()
    if code:
        path = os.path.join(FLAGS_DIR, f"{code}.png").replace('\\', '/')
        if os.path.exists(path): return path
    return None

def flag_img_html(country_name, size=80):
    """Return an <img> HTML tag for a country flag PNG, or empty string."""
    p = get_flag_path(country_name)
    if p: return f'<img src="file:///{p}" alt="{country_name}" style="height:{size}px;width:auto;border-radius:4px;">'
    return ""

TARGET_SITES = [
    {"name": "Onlinekhabar", "url": "https://www.onlinekhabar.com/content/business",
     "container_tag": "div",     "container_class": "ok-news-card", "title_tag": "h2"},
    {"name": "Ekantipur",    "url": "https://ekantipur.com/news",
     "container_tag": "article", "container_class": "normal",        "title_tag": "h2"},
    {"name": "Ratopati",     "url": "https://ratopati.com/province/koshi",
     "container_tag": "div",     "container_class": "item",           "title_tag": "h3"},
    {"name": "Setopati",     "url": "https://setopati.com/social",
     "container_tag": "div",     "container_class": "items",          "title_tag": "span"},
    {"name": "KhojSamachar", "url": "https://khojsamachar.com/",
     "container_tag": "article", "container_class": "post",           "title_tag": "h2"},
    {"name": "TechPana",     "url": "https://techpana.com/",
     "container_tag": "div",     "container_class": "item-details",   "title_tag": "h3"},
    {"name": "RONBPost",     "url": "https://www.ronbpost.com/",
     "container_tag": "article", "container_class": "post",           "title_tag": "h2"},
    {"name": "BBCNews",      "url": "https://www.bbc.com/news/world",
     "container_tag": "div",     "container_class": "sc-b8778340-3",  "title_tag": "h2"},
]

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def get_nepal_hour():
    return (datetime.now(timezone.utc) + NEPAL_TZ).hour

def get_nepal_now():
    return datetime.now(timezone.utc) + NEPAL_TZ

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f: return set(json.load(f))
        except: return set()
    return set()

def save_history(history_set):
    if not os.path.exists("data"): os.makedirs("data")
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(list(history_set)[-1000:], f, ensure_ascii=False, indent=4)

def cleanup_old_files():
    cutoff = time.time() - (48 * 3600)
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            fp = os.path.join(OUTPUT_DIR, f)
            if os.path.isfile(fp) and f.endswith('.png') and os.path.getmtime(fp) < cutoff:
                try: os.remove(fp)
                except: pass

def is_similar_duplicate(new_title, history_set):
    new_words = set(w for w in re.findall(r'\w+', new_title.lower()) if len(w) > 3)
    if not new_words: return False
    for old_title in history_set:
        old_words = set(w for w in re.findall(r'\w+', old_title.lower()) if len(w) > 3)
        if old_words and len(new_words.intersection(old_words)) / len(new_words) > 0.6:
            return True
    return False

def init_dirs():
    for d in [OUTPUT_DIR, POSTED_DIR, "data"]:
        if not os.path.exists(d): os.makedirs(d)

def make_hti(width=1080, height=1350):
    h = Html2Image(size=(width, height), browser_executable='google-chrome')
    h.output_path = OUTPUT_DIR
    h.browser.flags = [
        '--no-sandbox', '--disable-setuid-sandbox',
        '--allow-file-access-from-files', '--disable-dev-shm-usage'
    ]
    return h

# ============================================================
# AI PIPELINE (Groq → OpenRouter → Gemini with rotation)
# ============================================================
def generate_with_groq(prompt):
    if not GROQ_API_KEYS: return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    for key in GROQ_API_KEYS:
        try:
            res = requests.post(url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.4},
                timeout=20)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'].strip()
            print(f"    [Groq] Key {key[:8]}... → {res.status_code}")
        except Exception as e:
            print(f"    [Groq] Key {key[:8]}... exception: {e}")
    return None

def generate_with_openrouter(prompt):
    if not OPENROUTER_API_KEY: return None
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": "qwen/qwen-2.5-72b-instruct:free", "messages": [{"role": "user", "content": prompt}]},
            timeout=20)
        if res.status_code == 200: return res.json()['choices'][0]['message']['content'].strip()
    except: pass
    return None

def generate_with_gemini(prompt):
    if not GEMINI_API_KEYS: return None
    for key in GEMINI_API_KEYS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        try:
            res = requests.post(url,
                headers={'Content-Type': 'application/json'},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=20)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            print(f"    [Gemini] Key {key[:6]}... → {res.status_code}")
        except: pass
    return None

def ai_generate(prompt):
    """Try Groq → OpenRouter → Gemini in order."""
    for fn in [generate_with_groq, generate_with_openrouter, generate_with_gemini]:
        out = fn(prompt)
        if out: return out
    return None

# ============================================================
# SHARED: FACEBOOK POSTING
# ============================================================
def get_page_token():
    if not FB_PAGE_ACCESS_TOKEN or not FB_PAGE_ID: return None
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}?fields=access_token&access_token={FB_PAGE_ACCESS_TOKEN}"
    try:
        r = requests.get(url, timeout=10); data = r.json()
        if 'access_token' in data: return data['access_token']
        print(f"    [FB Token Error] {data}")
    except Exception as e: print(f"    [FB Exception] {e}")
    return None

def post_to_facebook(image_path, caption):
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        print("    [!] FB credentials missing."); return False
    if not os.path.exists(image_path):
        print(f"    [!] Image file missing: {image_path}"); return False
    if os.path.getsize(image_path) < 5000:
        print(f"    [!] Image too small (likely blank/error): {image_path}"); return False
    token = get_page_token()
    if not token: print("    [!] No page token."); return False
    try:
        with open(image_path, 'rb') as f:
            r = requests.post(
                f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/photos",
                data={'message': caption, 'access_token': token},
                files={'source': f}, timeout=60)
        if r.status_code == 200: print("    [OK] Posted to Facebook!"); return True
        err = r.json().get('error', {})
        print(f"    [FB Error {r.status_code}] {err.get('message', r.text[:200])}"); return False
    except Exception as e: print(f"    [FB Exception] {e}"); return False

# ============================================================
# SHARED: PEXELS IMAGE
# ============================================================
def get_pexels_image(keyword):
    if not PEXELS_API_KEY or not keyword: return None
    try:
        res = requests.get(f"https://api.pexels.com/v1/search?query={keyword}&per_page=1",
                           headers={"Authorization": PEXELS_API_KEY}, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get('photos'): return data['photos'][0]['src']['large2x']
    except: pass
    return None

# ============================================================
# MODE 1 — NEWS SCRAPER
# ============================================================
def fetch_full_article(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        if r.status_code != 200: return "", None
        soup = BeautifulSoup(r.text, 'html.parser')
        paras = [p.get_text(strip=True) for p in soup.find_all('p') if len(p.get_text(strip=True)) > 40]
        img_url = None
        for meta in ['og:image', 'twitter:image']:
            tag = soup.find('meta', property=meta) or soup.find('meta', attrs={'name': meta})
            if tag and tag.get('content'):
                img_url = tag['content']
                if not any(k in img_url.lower() for k in ['logo','default','placeholder','favicon']): break
                img_url = None
        return "\n".join(paras[:7]), img_url
    except: return "", None

def ai_rewrite_news(title, full_story):
    prompt = f"""You are an expert News Journalist. Read the following scraped text and generate content.
If the text is gibberish or not a real news article, output exactly: SKIP

STRICT RULES:
1. RED_BOX_1: Short, punchy, high-impact phrase (4-7 words)
2. RED_BOX_2: Secondary punchy phrase (2-5 words)
3. HEADLINE: Full, detailed headline (10-25 words)
4. CAPTION: Highly engaging, catchy news report for Facebook (3-4 paragraphs, 150-200 words). Strictly factual. NO EMOJIS. No exaggeration.
5. IMAGE_INTENT: PEXELS or ARTICLE

Original Title: {title}
Article Content:
---
{full_story}
---

Output Format (ONLY these 5 lines, or SKIP):
RED_BOX_1: [phrase]
RED_BOX_2: [phrase]
HEADLINE: [headline]
CAPTION: [caption]
IMAGE_INTENT: [ARTICLE or PEXELS]"""
    return ai_generate(prompt)

def parse_news_ai(output):
    box1, box2, headline, caption, intent = "BREAKING NEWS", "UPDATE", "News Update", "", "PEXELS"
    for line in output.split('\n'):
        if line.startswith('RED_BOX_1:'):   box1    = line.replace('RED_BOX_1:', '').strip()
        elif line.startswith('RED_BOX_2:'): box2    = line.replace('RED_BOX_2:', '').strip()
        elif line.startswith('HEADLINE:'):  headline = line.replace('HEADLINE:', '').strip()
        elif line.startswith('CAPTION:'):   caption  = line.replace('CAPTION:', '').strip()
        elif line.startswith('IMAGE_INTENT:'): intent = line.replace('IMAGE_INTENT:', '').strip().upper()
    return headline, box1, box2, caption, intent

def generate_news_card(headline, box1, box2, bg_image_url):
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1080px;height:1350px;font-family:'Inter',sans-serif;
background-image:url('{bg_image_url}');background-size:cover;background-position:center;
display:flex;flex-direction:column;justify-content:space-between;position:relative;overflow:hidden}}
.vignette{{position:absolute;top:0;left:0;right:0;bottom:0;
background:radial-gradient(circle at center,transparent 30%,rgba(0,0,0,0.4) 100%);z-index:1}}
.logo-wrap{{position:relative;z-index:10;margin:40px;align-self:flex-start;
background:rgba(0,0,0,0.2);backdrop-filter:blur(15px) saturate(120%);
-webkit-backdrop-filter:blur(15px) saturate(120%);border:1px solid rgba(255,255,255,0.15);
border-radius:20px;padding:12px 20px;box-shadow:0 8px 32px rgba(0,0,0,0.2)}}
.logo-wrap img{{height:70px;width:auto}}
.glass-card{{position:relative;z-index:10;margin:40px;margin-top:auto;
background:rgba(15,15,20,0.72);backdrop-filter:blur(35px) saturate(200%);
-webkit-backdrop-filter:blur(35px) saturate(200%);border:1px solid rgba(255,255,255,0.15);
border-top:1.5px solid rgba(255,255,255,0.35);border-radius:40px;
padding:55px 50px 40px;box-shadow:0 30px 60px rgba(0,0,0,0.55),inset 0 2px 2px rgba(255,255,255,0.08);
display:flex;flex-direction:column;align-items:center;text-align:center;gap:22px}}
.box-group{{display:flex;flex-direction:column;align-items:center;gap:8px}}
.redbox{{background:#d32f2f;color:#fff;font-size:30px;font-weight:800;
text-transform:uppercase;letter-spacing:1px;padding:10px 26px;border-radius:8px;
box-shadow:0 6px 20px rgba(211,47,47,0.45);display:inline-block}}
.headline{{font-size:30px;font-weight:700;line-height:1.5;color:#fff;
text-shadow:0 1px 5px rgba(0,0,0,0.3)}}
.divider{{width:100%;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.3),transparent)}}
.footer{{font-size:15px;font-weight:800;color:rgba(255,255,255,0.55);
letter-spacing:3px;text-transform:uppercase}}
.footer span{{color:#ff3b30}}
</style></head><body>
<div class="vignette"></div>
<div class="logo-wrap"><img src="file:///{LOGO_HTML}" alt="Logo"></div>
<div class="glass-card">
  <div class="box-group">
    <div class="redbox">{box1}</div>
    <div class="redbox">{box2}</div>
  </div>
  <div class="headline">{headline}</div>
  <div class="divider"></div>
  <div class="footer">NEPAL CENTRAL <span>NEWS</span></div>
</div></body></html>"""

def run_mode_1_news():
    print("\n[MODE 1] NEWS SCRAPER")
    history = load_history()
    hti = make_hti(1080, 1350)
    max_per_site = 5
    ready_to_post = []

    for site in TARGET_SITES:
        articles_found = 0
        print(f"  -> Scraping {site['name']}...")
        try:
            r = requests.get(site['url'], headers=HEADERS, timeout=15, verify=False)
            if r.status_code != 200: continue
            soup = BeautifulSoup(r.text, 'html.parser')
            containers = soup.find_all(site['container_tag'], class_=site['container_class'])
            if not containers: containers = soup.find_all(site['container_tag'])

            for container in containers:
                if articles_found >= max_per_site: break
                title_tag = container.find(site['title_tag'])
                if not title_tag: continue
                title_text = title_tag.get_text(strip=True)
                if not title_text or len(title_text) < 15: continue
                if title_text in history or is_similar_duplicate(title_text, history): continue

                link_tag = container.find('a', href=True) or title_tag.find('a', href=True)
                full_link = urljoin(site['url'], link_tag['href']) if link_tag else site['url']

                print(f"    [Fetch] {title_text[:50]}...")
                full_story, bg_img = fetch_full_article(full_link)
                if not full_story: full_story = title_text

                ai_out = ai_rewrite_news(title_text, full_story)
                if not ai_out: print("    [Skip] AI failed."); continue
                if ai_out.strip() == "SKIP": print("    [Skip] AI flagged as non-news."); continue

                headline, box1, box2, caption, intent = parse_news_ai(ai_out)
                articles_found += 1
                history.add(title_text)

                bg_final = None
                kw = box1
                if intent == "PEXELS":
                    bg_final = get_pexels_image(kw) or bg_img
                else:
                    bg_final = bg_img or get_pexels_image(kw)
                if not bg_final:
                    bg_final = "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=1080&h=1350&fit=crop"

                html = generate_news_card(headline, box1, box2, bg_final)
                safe = re.sub(r'[^a-zA-Z0-9]', '_', headline)[:50]
                fname = f"news_{safe}_{int(time.time())}.png"
                hti.screenshot(html_str=html, save_as=fname)
                time.sleep(2)  # let Chrome write the file
                img_path = os.path.join(OUTPUT_DIR, fname)
                if not os.path.exists(img_path) or os.path.getsize(img_path) < 5000:
                    print(f"    [Skip] Image generation failed for: {fname}"); continue
                ready_to_post.append((img_path, caption, fname))

        except Exception as e:
            print(f"    [ERROR] {site['name']}: {e}")
        time.sleep(1)

    if not ready_to_post:
        print("  [-] No new articles found.")
    else:
        print(f"\n  [+] {len(ready_to_post)} articles ready. Uploading...")
        max_wait = 1200
        avg_wait = max(30, max_wait // len(ready_to_post))
        for i, (img_path, caption, fname) in enumerate(ready_to_post):
            success = post_to_facebook(img_path, caption)
            if success:
                try:
                    shutil.move(img_path, os.path.join(POSTED_DIR, fname))
                except Exception:
                    pass
            if i < len(ready_to_post) - 1:
                delay = random.randint(30, avg_wait * 2)
                print(f"    [Anti-Spam] Sleeping {delay/60:.1f} min...")
                time.sleep(delay)

    save_history(history)

# ============================================================
# MODE 2 — NEPAL GOLD & SILVER RATES
# ============================================================
def scrape_gold_rates():
    try:
        r = requests.get("https://www.fenegosida.org/", headers=HEADERS, timeout=15, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
        rates = {}
        # Try to find rate table
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                text = ' '.join(cells).lower()
                if 'fine' in text or '24' in text or 'tejabi' in text or 'silver' in text:
                    if len(cells) >= 2:
                        val = ''.join(c for c in cells[-1] if c.isdigit() or c in '.,')
                        if 'fine' in text or '24' in text: rates['fine_gold'] = val
                        elif 'tejabi' in text:              rates['tejabi']    = val
                        elif 'silver' in text:              rates['silver']    = val
        if rates: return rates
        # Fallback: search for price text
        for tag in soup.find_all(['p', 'div', 'span', 'li']):
            txt = tag.get_text(strip=True)
            if 'Fine' in txt and 'Rs' in txt:
                nums = re.findall(r'[\d,]+', txt)
                if nums: rates['fine_gold'] = rates.get('fine_gold', nums[0])
            if 'Tejabi' in txt:
                nums = re.findall(r'[\d,]+', txt)
                if nums: rates['tejabi'] = rates.get('tejabi', nums[0])
            if 'Silver' in txt:
                nums = re.findall(r'[\d,]+', txt)
                if nums: rates['silver'] = rates.get('silver', nums[0])
        return rates if rates else None
    except Exception as e:
        print(f"  [Gold Scrape Error] {e}")
        return None

def generate_gold_card(fine_gold, tejabi, silver, date_str):
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1080px;height:1350px;font-family:'Inter',sans-serif;
background:linear-gradient(135deg,#0a0a0a 0%,#1a1400 50%,#0a0a0a 100%);
display:flex;flex-direction:column;align-items:center;justify-content:center;
position:relative;overflow:hidden}}
.glow{{position:absolute;width:700px;height:700px;border-radius:50%;
background:radial-gradient(circle,rgba(212,175,55,0.12) 0%,transparent 70%);
top:50%;left:50%;transform:translate(-50%,-50%);z-index:0}}
.stripe{{position:absolute;top:0;left:0;right:0;height:8px;
background:linear-gradient(90deg,#b8860b,#ffd700,#b8860b)}}
.stripe-bottom{{position:absolute;bottom:0;left:0;right:0;height:8px;
background:linear-gradient(90deg,#b8860b,#ffd700,#b8860b)}}
.logo-wrap{{position:absolute;top:40px;left:40px;z-index:10;
background:rgba(0,0,0,0.4);backdrop-filter:blur(12px);
border:1px solid rgba(212,175,55,0.3);border-radius:16px;padding:10px 18px}}
.logo-wrap img{{height:60px;width:auto}}
.card{{position:relative;z-index:2;width:920px;
background:rgba(10,10,5,0.85);
backdrop-filter:blur(30px) saturate(180%);
-webkit-backdrop-filter:blur(30px) saturate(180%);
border:1px solid rgba(212,175,55,0.25);
border-top:2px solid rgba(212,175,55,0.6);
border-radius:40px;padding:60px 65px;
box-shadow:0 40px 80px rgba(0,0,0,0.8),0 0 60px rgba(212,175,55,0.06),
           inset 0 1px 0 rgba(212,175,55,0.15);
display:flex;flex-direction:column;align-items:center;gap:40px}}
.top-badge{{background:linear-gradient(135deg,rgba(212,175,55,0.2),rgba(212,175,55,0.04));
border:1px solid rgba(212,175,55,0.5);border-radius:100px;padding:10px 28px;
font-size:18px;font-weight:700;color:#d4af37;letter-spacing:2px;text-transform:uppercase}}
.title{{font-size:52px;font-weight:900;color:#ffd700;
background:linear-gradient(135deg,#ffd700,#b8860b,#ffd700);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;
text-align:center;letter-spacing:-1px}}
.subtitle{{font-size:22px;font-weight:600;color:rgba(212,175,55,0.6);
letter-spacing:1px;text-transform:uppercase}}
.rates{{display:flex;flex-direction:column;width:100%;gap:18px}}
.rate-row{{display:flex;justify-content:space-between;align-items:center;
background:rgba(212,175,55,0.06);border:1px solid rgba(212,175,55,0.15);
border-radius:20px;padding:25px 35px}}
.rate-label{{font-size:26px;font-weight:700;color:rgba(255,255,255,0.8)}}
.rate-label span{{display:block;font-size:16px;font-weight:500;color:rgba(255,255,255,0.4);margin-top:4px}}
.rate-value{{font-size:38px;font-weight:900;color:#ffd700;letter-spacing:-1px}}
.rate-value small{{font-size:18px;color:rgba(212,175,55,0.6)}}
.sep{{width:100%;height:1px;background:linear-gradient(90deg,transparent,rgba(212,175,55,0.3),transparent)}}
.footer{{display:flex;justify-content:space-between;align-items:center;width:100%}}
.brand{{font-size:17px;font-weight:800;color:rgba(255,255,255,0.45);
letter-spacing:3px;text-transform:uppercase}}
.brand span{{color:#ffd700}}
.date{{font-size:17px;font-weight:600;color:rgba(212,175,55,0.5)}}
</style></head><body>
<div class="glow"></div>
<div class="stripe"></div>
<div class="stripe-bottom"></div>
<div class="logo-wrap"><img src="file:///{LOGO_HTML}" alt="Logo"></div>
<div class="card">
  <div class="top-badge">&#128178; Today's Market Rates</div>
  <div>
    <div class="title">Nepal Gold &amp; Silver</div>
    <div class="subtitle" style="text-align:center;margin-top:10px">Daily Price Update — Per Tola</div>
  </div>
  <div class="rates">
    <div class="rate-row">
      <div class="rate-label">Fine Gold (24K)<span>Shuddha Suna</span></div>
      <div class="rate-value">Rs. {fine_gold}<small>/tola</small></div>
    </div>
    <div class="rate-row">
      <div class="rate-label">Tejabi Gold<span>Tejabi Suna</span></div>
      <div class="rate-value">Rs. {tejabi}<small>/tola</small></div>
    </div>
    <div class="rate-row" style="border-color:rgba(192,192,192,0.2);background:rgba(192,192,192,0.05)">
      <div class="rate-label" style="color:rgba(210,210,210,0.8)">Silver<span>Chandi</span></div>
      <div class="rate-value" style="color:#c0c0c0">Rs. {silver}<small>/tola</small></div>
    </div>
  </div>
  <div class="sep"></div>
  <div class="footer">
    <div class="brand">NEPAL CENTRAL <span>NEWS</span></div>
    <div class="date">&#128197; {date_str}</div>
  </div>
</div></body></html>"""

def run_mode_2_gold():
    print("\n[MODE 2] GOLD & SILVER RATES")
    history = load_history()
    today_key = f"GOLD_{get_nepal_now().strftime('%Y-%m-%d')}"
    if today_key in history:
        print("  [Skip] Gold rates already posted today."); return
    rates = scrape_gold_rates()
    if not rates:
        print("  [!] Could not scrape gold rates."); return

    fine = rates.get('fine_gold', 'N/A')
    tej  = rates.get('tejabi', 'N/A')
    silv = rates.get('silver', 'N/A')
    date_str = get_nepal_now().strftime("%B %d, %Y")

    print(f"  [Rates] Fine={fine}  Tejabi={tej}  Silver={silv}")
    hti = make_hti(1080, 1350)
    html = generate_gold_card(fine, tej, silv, date_str)
    fname = f"gold_{get_nepal_now().strftime('%Y%m%d')}.png"
    hti.screenshot(html_str=html, save_as=fname)
    time.sleep(2)
    img_path = os.path.join(OUTPUT_DIR, fname)

    if os.path.exists(img_path) and os.path.getsize(img_path) > 5000:
        if post_to_facebook(img_path, caption):
            try:
                shutil.move(img_path, os.path.join(POSTED_DIR, fname))
            except Exception: pass
            history.add(today_key)
            save_history(history)
    else:
        print("  [!] Image generation failed or file is too small.")

# ============================================================
# MODE 3 — WIKIPEDIA "ON THIS DAY"
# ============================================================
def fetch_on_this_day():
    now = get_nepal_now()
    month, day = now.month, now.day
    try:
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/all/{month}/{day}",
            headers={"Accept": "application/json"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            events = data.get('events', []) + data.get('births', []) + data.get('deaths', [])
            # Pick a significant event (shuffle and pick first with good text)
            random.shuffle(events)
            for ev in events[:10]:
                text = ev.get('text', '')
                year = ev.get('year', '')
                if len(text) > 50:
                    return f"On this day in {year}: {text}"
    except Exception as e:
        print(f"  [WikiAPI Error] {e}")
    return None

def ai_rewrite_otd(raw_event):
    prompt = f"""You are a creative historian and journalist. Read this historical event and generate content:

Event: {raw_event}

STRICT RULES:
1. HEADLINE: A catchy, short headline (6-10 words). Title Case.
2. BODY: One captivating sentence (20-28 words) that explains the event. Make it feel dramatic and significant.
3. YEAR: Just the 4-digit year.
4. CAPTION: 2 paragraphs (80-100 words total) about this event for Facebook. Factual, engaging, NO emojis.

Output Format (ONLY these 4 lines):
HEADLINE: [headline]
BODY: [body sentence]
YEAR: [year]
CAPTION: [caption]"""
    return ai_generate(prompt)

def parse_otd_ai(output):
    headline, body, year, caption = "On This Day", "A historical event occurred.", "—", ""
    for line in output.split('\n'):
        if line.startswith('HEADLINE:'): headline = line.replace('HEADLINE:', '').strip()
        elif line.startswith('BODY:'):   body     = line.replace('BODY:', '').strip()
        elif line.startswith('YEAR:'):   year     = line.replace('YEAR:', '').strip()
        elif line.startswith('CAPTION:'): caption = line.replace('CAPTION:', '').strip()
    return headline, body, year, caption

def generate_otd_card(headline, body, year, month_day):
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1080px;height:1350px;font-family:'Playfair Display',serif;
background:linear-gradient(160deg,#1a1510 0%,#0d0c09 40%,#1a1510 100%);
display:flex;flex-direction:column;align-items:center;justify-content:center;
position:relative;overflow:hidden}}
.noise{{position:absolute;top:0;left:0;right:0;bottom:0;opacity:0.04;
background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
background-size:200px}}
.corner-tl{{position:absolute;top:40px;left:40px;width:80px;height:80px;
border-top:3px solid rgba(210,180,100,0.4);border-left:3px solid rgba(210,180,100,0.4)}}
.corner-br{{position:absolute;bottom:40px;right:40px;width:80px;height:80px;
border-bottom:3px solid rgba(210,180,100,0.4);border-right:3px solid rgba(210,180,100,0.4)}}
.logo-wrap{{position:absolute;top:40px;left:50%;transform:translateX(-50%);z-index:10;
background:rgba(0,0,0,0.5);backdrop-filter:blur(10px);
border:1px solid rgba(210,180,100,0.2);border-radius:16px;padding:10px 18px}}
.logo-wrap img{{height:55px;width:auto;filter:grayscale(30%)}}
.main{{position:relative;z-index:2;width:900px;display:flex;flex-direction:column;
align-items:center;gap:40px;padding:40px}}
.otd-badge{{font-family:'Inter',sans-serif;background:transparent;
border:1.5px solid rgba(210,180,100,0.5);border-radius:100px;padding:10px 30px;
font-size:17px;font-weight:600;color:rgba(210,180,100,0.8);
letter-spacing:4px;text-transform:uppercase}}
.year-stamp{{font-size:160px;font-weight:900;color:transparent;
-webkit-text-stroke:2px rgba(210,180,100,0.15);line-height:1;
letter-spacing:-8px;position:absolute;top:50%;left:50%;
transform:translate(-50%,-50%);white-space:nowrap;z-index:0}}
.date-line{{font-family:'Inter',sans-serif;font-size:18px;font-weight:500;
color:rgba(210,180,100,0.5);letter-spacing:3px;text-transform:uppercase}}
.divider{{display:flex;align-items:center;gap:20px;width:100%}}
.divider-line{{flex:1;height:1px;background:linear-gradient(90deg,transparent,rgba(210,180,100,0.3))}}
.divider-icon{{font-size:20px;color:rgba(210,180,100,0.5)}}
.divider-line.rev{{background:linear-gradient(90deg,rgba(210,180,100,0.3),transparent)}}
.headline{{font-size:58px;font-weight:900;line-height:1.15;color:#e8dcc8;
text-align:center;letter-spacing:-1px;text-shadow:0 4px 20px rgba(0,0,0,0.5)}}
.body{{font-family:'Inter',sans-serif;font-size:26px;font-weight:400;line-height:1.7;
color:rgba(220,205,180,0.75);text-align:center;max-width:820px}}
.sep{{width:60px;height:3px;background:linear-gradient(90deg,#b8860b,#ffd700,#b8860b);
border-radius:2px}}
.footer{{font-family:'Inter',sans-serif;display:flex;justify-content:space-between;
align-items:center;width:100%;margin-top:10px}}
.brand{{font-size:16px;font-weight:800;color:rgba(255,255,255,0.4);
letter-spacing:3px;text-transform:uppercase}}
.brand span{{color:rgba(210,180,100,0.7)}}
.hashtag{{font-size:15px;font-weight:600;color:rgba(210,180,100,0.4)}}
</style></head><body>
<div class="noise"></div>
<div class="corner-tl"></div>
<div class="corner-br"></div>
<div class="logo-wrap"><img src="file:///{LOGO_HTML}" alt="Logo"></div>
<div class="main">
  <div class="otd-badge">&#9881; On This Day in History</div>
  <div class="date-line">{month_day}</div>
  <div class="divider">
    <div class="divider-line"></div>
    <div class="divider-icon">&#11835;</div>
    <div class="divider-line rev"></div>
  </div>
  <div class="headline">{headline}</div>
  <div class="sep"></div>
  <div class="body">{body}</div>
  <div class="divider">
    <div class="divider-line"></div>
    <div class="divider-icon">&#11835;</div>
    <div class="divider-line rev"></div>
  </div>
  <div class="footer">
    <div class="brand">NEPAL CENTRAL <span>NEWS</span></div>
    <div class="hashtag">#OnThisDay #History</div>
  </div>
</div>
<div class="year-stamp">{year}</div>
</body></html>"""

def run_mode_3_otd():
    print("\n[MODE 3] ON THIS DAY — Wikipedia")
    history = load_history()
    now = get_nepal_now()
    today_key = f"OTD_{now.strftime('%Y-%m-%d')}"
    if today_key in history:
        print("  [Skip] On This Day already posted today."); return

    raw_event = fetch_on_this_day()
    if not raw_event:
        print("  [!] Could not fetch Wikipedia data."); return

    print(f"  [Event] {raw_event[:80]}...")
    ai_out = ai_rewrite_otd(raw_event)
    if not ai_out: print("  [!] AI failed."); return

    headline, body, year, caption = parse_otd_ai(ai_out)
    month_day = now.strftime("%B %d")

    print(f"  [Headline] {headline}")
    hti = make_hti(1080, 1350)
    html = generate_otd_card(headline, body, year, month_day)
    fname = f"otd_{now.strftime('%Y%m%d')}.png"
    hti.screenshot(html_str=html, save_as=fname)
    time.sleep(2)
    img_path = os.path.join(OUTPUT_DIR, fname)

    full_caption = f"""On This Day in History — {month_day}

{headline}

{caption}

Follow Nepal Central News for daily historical facts, news, and updates from Nepal and around the world!
#OnThisDay #History #NepalCentralNews #DidYouKnow"""

    if os.path.exists(img_path) and os.path.getsize(img_path) > 5000:
        if post_to_facebook(img_path, full_caption):
            try:
                shutil.move(img_path, os.path.join(POSTED_DIR, fname))
            except Exception: pass
            history.add(today_key)
            save_history(history)
    else:
        print("  [!] Image generation failed or file is too small.")

# ============================================================
# MODE 4 — POP CULTURE TRIVIA (AI-Generated)
# ============================================================
def ai_generate_trivia(date_str):
    prompt = f"""You are a viral social media content creator. Today's date is {date_str}.

Generate ONE highly engaging pop culture milestone, iconic movie/music trivia, or globally trending celebrity fact that is connected to today's date OR is currently trending/relevant globally.

STRICT RULES:
1. HEADLINE: Catchy, viral-worthy (6-9 words). Title Case.
2. BODY: One fascinating, mind-blowing sentence (20-26 words).
3. HIGHLIGHT: One single keyword from BODY to highlight (for neon glow effect).
4. CAPTION: 2 punchy paragraphs (80-100 words) for Facebook. Engaging and fun. No emojis.
5. KEYWORD: One word for image search (e.g. music, cinema, celebrity, sports).

Output Format (ONLY these 5 lines):
HEADLINE: [headline]
BODY: [body]
HIGHLIGHT: [word]
CAPTION: [caption]
KEYWORD: [word]"""
    return ai_generate(prompt)

def parse_trivia_ai(output):
    headline, body, highlight, caption, keyword = "Pop Culture Fact", "An amazing fact.", "amazing", "", "entertainment"
    for line in output.split('\n'):
        if line.startswith('HEADLINE:'):   headline  = line.replace('HEADLINE:', '').strip()
        elif line.startswith('BODY:'):     body      = line.replace('BODY:', '').strip()
        elif line.startswith('HIGHLIGHT:'): highlight = line.replace('HIGHLIGHT:', '').strip()
        elif line.startswith('CAPTION:'):  caption   = line.replace('CAPTION:', '').strip()
        elif line.startswith('KEYWORD:'):  keyword   = line.replace('KEYWORD:', '').strip()
    return headline, body, highlight, caption, keyword

def highlight_word(text, word):
    if not word or word.lower() == 'none': return text
    pattern = re.compile(re.escape(word), re.IGNORECASE)
    return pattern.sub(lambda m: f'<span class="hl">{m.group(0)}</span>', text)

def generate_trivia_card(headline, body, highlight, bg_url):
    body_html = highlight_word(body, highlight)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700;800&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1080px;height:1350px;font-family:'Space Grotesk',sans-serif;
background-image:url('{bg_url}');background-size:cover;background-position:center;
display:flex;flex-direction:column;justify-content:space-between;
position:relative;overflow:hidden}}
.overlay{{position:absolute;top:0;left:0;right:0;bottom:0;
background:linear-gradient(160deg,rgba(20,0,40,0.7) 0%,rgba(5,0,20,0.5) 50%,rgba(40,0,60,0.85) 100%);
z-index:1}}
.scanlines{{position:absolute;top:0;left:0;right:0;bottom:0;z-index:1;
background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,0.03) 3px,rgba(0,0,0,0.03) 4px)}}
.logo-wrap{{position:relative;z-index:10;margin:40px;align-self:flex-start;
background:rgba(0,0,0,0.3);backdrop-filter:blur(10px);
border:1px solid rgba(255,0,255,0.2);border-radius:16px;padding:10px 18px}}
.logo-wrap img{{height:60px;width:auto}}
.neon-card{{position:relative;z-index:10;margin:40px;margin-top:auto;
background:rgba(5,0,20,0.75);backdrop-filter:blur(30px) saturate(200%);
-webkit-backdrop-filter:blur(30px) saturate(200%);
border:1px solid rgba(180,0,255,0.3);
border-top:2px solid rgba(255,0,200,0.6);
border-radius:40px;padding:55px 50px 40px;
box-shadow:0 0 60px rgba(180,0,255,0.15),0 30px 60px rgba(0,0,0,0.7),
           inset 0 1px 0 rgba(255,255,255,0.06);
display:flex;flex-direction:column;align-items:center;text-align:center;gap:24px}}
.badge{{background:linear-gradient(135deg,rgba(255,0,200,0.2),rgba(150,0,255,0.1));
border:1px solid rgba(255,0,200,0.4);border-radius:100px;padding:10px 28px;
font-size:16px;font-weight:700;color:#ff00c8;
letter-spacing:3px;text-transform:uppercase;
text-shadow:0 0 10px rgba(255,0,200,0.5)}}
.headline{{font-size:52px;font-weight:800;line-height:1.2;
background:linear-gradient(135deg,#ff00c8,#a855f7,#00d4ff);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;
letter-spacing:-1px}}
.body{{font-family:'Inter',sans-serif;font-size:26px;font-weight:500;
line-height:1.65;color:rgba(220,200,255,0.85)}}
.hl{{color:#ff00c8;font-weight:700;text-shadow:0 0 15px rgba(255,0,200,0.6)}}
.sep{{width:100%;height:1px;
background:linear-gradient(90deg,transparent,rgba(255,0,200,0.35),rgba(168,85,247,0.35),transparent)}}
.footer{{display:flex;justify-content:space-between;align-items:center;width:100%}}
.brand{{font-size:15px;font-weight:800;color:rgba(255,255,255,0.45);
letter-spacing:3px;text-transform:uppercase}}
.brand span{{color:#ff00c8;text-shadow:0 0 8px rgba(255,0,200,0.4)}}
.tag{{font-size:15px;font-weight:700;color:rgba(168,85,247,0.6)}}
</style></head><body>
<div class="overlay"></div>
<div class="scanlines"></div>
<div class="logo-wrap"><img src="file:///{LOGO_HTML}" alt="Logo"></div>
<div class="neon-card">
  <div class="badge">&#9733; Pop Culture</div>
  <div class="headline">{headline}</div>
  <div class="body">{body_html}</div>
  <div class="sep"></div>
  <div class="footer">
    <div class="brand">NEPAL CENTRAL <span>NEWS</span></div>
    <div class="tag">#PopCulture #Trending</div>
  </div>
</div></body></html>"""

def run_mode_4_trivia():
    print("\n[MODE 4] POP CULTURE TRIVIA")
    history = load_history()
    now = get_nepal_now()
    today_key = f"TRIVIA_{now.strftime('%Y-%m-%d')}"
    if today_key in history:
        print("  [Skip] Trivia already posted today."); return

    date_str = now.strftime("%B %d, %Y")
    ai_out = ai_generate_trivia(date_str)
    if not ai_out: print("  [!] AI failed."); return

    headline, body, highlight, caption, keyword = parse_trivia_ai(ai_out)
    print(f"  [Trivia] {headline}")

    bg_url = get_pexels_image(keyword) or "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=1080&h=1350&fit=crop"

    hti = make_hti(1080, 1350)
    html = generate_trivia_card(headline, body, highlight, bg_url)
    fname = f"trivia_{now.strftime('%Y%m%d')}.png"
    hti.screenshot(html_str=html, save_as=fname)
    time.sleep(2)
    img_path = os.path.join(OUTPUT_DIR, fname)

    full_caption = f"""Pop Culture Fact of the Day

{headline}

{caption}

Follow Nepal Central News for daily trivia, news updates, and entertainment facts!
#PopCulture #Trending #DidYouKnow #NepalCentralNews"""

    if os.path.exists(img_path) and os.path.getsize(img_path) > 5000:
        if post_to_facebook(img_path, full_caption):
            try:
                shutil.move(img_path, os.path.join(POSTED_DIR, fname))
            except Exception: pass
            history.add(today_key)
            save_history(history)
    else:
        print("  [!] Image generation failed or file is too small.")

# ============================================================
# MODE 5 — NASA APOD
# ============================================================
def fetch_nasa_apod():
    try:
        r = requests.get(f"https://api.nasa.gov/planetary/apod?api_key={NASA_API_KEY}", timeout=15)
        if r.status_code == 200:
            data = r.json()
            return {
                'title': data.get('title', ''),
                'explanation': data.get('explanation', ''),
                'url': data.get('hdurl') or data.get('url', ''),
                'date': data.get('date', ''),
                'media_type': data.get('media_type', 'image')
            }
    except Exception as e:
        print(f"  [NASA Error] {e}")
    return None

def ai_rewrite_apod(title, explanation):
    prompt = f"""You are a science communicator for a news page. Read this NASA Astronomy Picture of the Day and generate content:

Title: {title}
Explanation: {explanation}

STRICT RULES:
1. HEADLINE: Mind-blowing, awe-inspiring (6-9 words). Title Case.
2. BODY: One captivating space fact sentence (22-26 words). Make it feel epic.
3. CAPTION: 2-3 paragraphs (100-130 words) for Facebook. Fascinating, accurate, NO emojis.

Output Format (ONLY these 3 lines):
HEADLINE: [headline]
BODY: [body]
CAPTION: [caption]"""
    return ai_generate(prompt)

def parse_apod_ai(output):
    headline, body, caption = "The Universe Revealed", "NASA reveals a breathtaking view of our cosmos.", ""
    for line in output.split('\n'):
        if line.startswith('HEADLINE:'): headline = line.replace('HEADLINE:', '').strip()
        elif line.startswith('BODY:'):   body     = line.replace('BODY:', '').strip()
        elif line.startswith('CAPTION:'): caption = line.replace('CAPTION:', '').strip()
    return headline, body, caption

def generate_apod_card(headline, body, bg_url, apod_title):
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1080px;height:1350px;font-family:'Inter',sans-serif;
background-image:url('{bg_url}');background-size:cover;background-position:center;
display:flex;flex-direction:column;justify-content:space-between;
position:relative;overflow:hidden}}
.overlay{{position:absolute;top:0;left:0;right:0;bottom:0;
background:linear-gradient(160deg,rgba(0,5,20,0.3) 0%,rgba(0,0,10,0.2) 40%,rgba(0,0,20,0.9) 80%,rgba(0,0,30,0.97) 100%);
z-index:1}}
.stars{{position:absolute;top:0;left:0;right:0;bottom:0;z-index:0;
background-image:radial-gradient(1px 1px at 20% 30%,rgba(255,255,255,0.8),transparent),
  radial-gradient(1px 1px at 80% 10%,rgba(255,255,255,0.6),transparent),
  radial-gradient(1px 1px at 60% 70%,rgba(255,255,255,0.5),transparent),
  radial-gradient(2px 2px at 10% 80%,rgba(100,200,255,0.4),transparent),
  radial-gradient(1px 1px at 90% 90%,rgba(255,255,255,0.7),transparent)}}
.logo-wrap{{position:relative;z-index:10;margin:40px;align-self:flex-start;
background:rgba(0,0,30,0.4);backdrop-filter:blur(12px);
border:1px solid rgba(100,150,255,0.2);border-radius:16px;padding:10px 18px}}
.logo-wrap img{{height:60px;width:auto}}
.space-card{{position:relative;z-index:10;margin:30px;margin-top:auto;
background:rgba(0,5,25,0.8);backdrop-filter:blur(40px) saturate(200%);
-webkit-backdrop-filter:blur(40px) saturate(200%);
border:1px solid rgba(100,150,255,0.2);
border-top:2px solid rgba(100,200,255,0.5);
border-radius:40px;padding:55px 50px 40px;
box-shadow:0 0 80px rgba(0,50,200,0.15),0 40px 80px rgba(0,0,0,0.8),
           inset 0 1px 0 rgba(100,200,255,0.1);
display:flex;flex-direction:column;align-items:center;text-align:center;gap:24px}}
.nasa-badge{{background:rgba(0,20,80,0.5);border:1px solid rgba(100,150,255,0.4);
border-radius:100px;padding:10px 24px;
font-size:16px;font-weight:700;color:#64b4ff;letter-spacing:2px;text-transform:uppercase;
box-shadow:0 0 20px rgba(100,150,255,0.1)}}
.headline{{font-size:52px;font-weight:900;line-height:1.2;
background:linear-gradient(135deg,#ffffff,#a8d0ff,#6090ff);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;
letter-spacing:-1px}}
.apod-label{{font-size:16px;font-weight:500;color:rgba(150,180,255,0.5);
letter-spacing:1px;font-style:italic}}
.body{{font-size:26px;font-weight:400;line-height:1.65;
color:rgba(200,220,255,0.8)}}
.sep{{width:100%;height:1px;
background:linear-gradient(90deg,transparent,rgba(100,180,255,0.3),transparent)}}
.footer{{display:flex;justify-content:space-between;align-items:center;width:100%}}
.brand{{font-size:15px;font-weight:800;color:rgba(255,255,255,0.4);
letter-spacing:3px;text-transform:uppercase}}
.brand span{{color:#4da6ff}}
.nasa-tag{{font-size:15px;font-weight:700;color:rgba(100,150,255,0.5)}}
</style></head><body>
<div class="stars"></div>
<div class="overlay"></div>
<div class="logo-wrap"><img src="file:///{LOGO_HTML}" alt="Logo"></div>
<div class="space-card">
  <div class="nasa-badge">&#127756; NASA — Astronomy Picture of the Day</div>
  <div class="headline">{headline}</div>
  <div class="apod-label">"{apod_title}"</div>
  <div class="body">{body}</div>
  <div class="sep"></div>
  <div class="footer">
    <div class="brand">NEPAL CENTRAL <span>NEWS</span></div>
    <div class="nasa-tag">#NASAApod #Space</div>
  </div>
</div></body></html>"""

def run_mode_5_nasa():
    print("\n[MODE 5] NASA APOD")
    history = load_history()
    now = get_nepal_now()
    today_key = f"NASA_{now.strftime('%Y-%m-%d')}"
    if today_key in history:
        print("  [Skip] NASA APOD already posted today."); return

    apod = fetch_nasa_apod()
    if not apod: print("  [!] Could not fetch NASA APOD."); return
    if apod['media_type'] != 'image':
        print(f"  [Skip] APOD is not an image today (type={apod['media_type']})."); return

    print(f"  [APOD] {apod['title']}")
    ai_out = ai_rewrite_apod(apod['title'], apod['explanation'])
    if not ai_out: print("  [!] AI failed."); return

    headline, body, caption = parse_apod_ai(ai_out)

    hti = make_hti(1080, 1350)
    html = generate_apod_card(headline, body, apod['url'], apod['title'])
    fname = f"nasa_{now.strftime('%Y%m%d')}.png"
    hti.screenshot(html_str=html, save_as=fname)
    time.sleep(2)
    img_path = os.path.join(OUTPUT_DIR, fname)

    full_caption = f"""NASA Astronomy Picture of the Day

{headline}

{caption}

Credit: NASA / {apod.get('copyright', 'ESA')}

Follow Nepal Central News for daily space discoveries and science updates!
#NASA #APOD #Space #Astronomy #NepalCentralNews #Universe"""

    if os.path.exists(img_path) and os.path.getsize(img_path) > 5000:
        if post_to_facebook(img_path, full_caption):
            try:
                shutil.move(img_path, os.path.join(POSTED_DIR, fname))
            except Exception: pass
            history.add(today_key)
            save_history(history)
    else:
        print("  [!] Image generation failed or file is too small.")

# ============================================================
# MAIN DISPATCHER
# ============================================================
def main():
    init_dirs()
    cleanup_old_files()
    hour = get_nepal_hour()
    now = get_nepal_now()

    print(f"\n{'='*60}")
    print(f"  Nepal Central News — Multi-Content Engine")
    print(f"  Nepal Time: {now.strftime('%I:%M %p, %b %d %Y')}  |  Hour: {hour}")
    print(f"{'='*60}")

    if 10 <= hour <= 12:
        print("  → Dispatching: MODE 2 — Gold & Silver Rates")
        run_mode_2_gold()
    elif 13 <= hour <= 16:
        print("  → Dispatching: MODE 3 — On This Day")
        run_mode_3_otd()
    elif 17 <= hour <= 20:
        print("  → Dispatching: MODE 4 — Pop Culture Trivia")
        run_mode_4_trivia()
    elif hour >= 21:
        print("  → Dispatching: MODE 5 — NASA APOD")
        run_mode_5_nasa()
    else:
        print("  → Dispatching: MODE 1 — News Scraper")
        run_mode_1_news()

    print(f"\n{'='*60}")
    print("  Engine Complete!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
