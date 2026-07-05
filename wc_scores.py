# -*- coding: utf-8 -*-
"""
FIFA World Cup 2026 - Automated Score Poster for Nepal Central News
"""
import requests, time, os, json, re
from html2image import Html2Image
from datetime import datetime, timezone, timedelta

FOOTBALL_API_KEY     = os.environ.get("FOOTBALL_API_KEY")
FB_PAGE_ID           = os.environ.get("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN")

NEPAL_TZ_OFFSET = timedelta(hours=5, minutes=45)
HEADERS_FOOTBALL = {"X-Auth-Token": FOOTBALL_API_KEY}
BASE_URL = "https://api.football-data.org/v4"
OUTPUT_DIR = "wc_output"
POSTED_DIR = "wc_posted"
WC_HISTORY_FILE = "data/wc_posted_history.json"
ASSETS_DIR = os.path.abspath("assets")
FLAGS_DIR = os.path.join(ASSETS_DIR, "Flag PNG")

# Map team name → ISO 3166-1 alpha-2 country code (for PNG flags)
COUNTRY_CODE_MAP = {
    "Argentina": "ar", "Brazil": "br", "France": "fr", "Germany": "de",
    "Spain": "es", "England": "gb-eng", "Portugal": "pt", "Netherlands": "nl",
    "Belgium": "be", "Italy": "it", "Croatia": "hr", "Uruguay": "uy",
    "Mexico": "mx", "United States": "us", "Canada": "ca", "Morocco": "ma",
    "Senegal": "sn", "Japan": "jp", "South Korea": "kr", "Australia": "au",
    "Saudi Arabia": "sa", "Iran": "ir", "Switzerland": "ch", "Denmark": "dk",
    "Poland": "pl", "Serbia": "rs", "Ukraine": "ua", "Colombia": "co",
    "Ecuador": "ec", "Peru": "pe", "Chile": "cl", "Venezuela": "ve",
    "Egypt": "eg", "Nigeria": "ng", "Cameroon": "cm", "Ghana": "gh",
    "Norway": "no", "Sweden": "se", "Turkey": "tr", "Austria": "at",
    "Czech Republic": "cz", "Hungary": "hu", "Slovakia": "sk", "Romania": "ro",
    "Scotland": "gb-sct", "Wales": "gb-wls", "Ireland": "ie", "Greece": "gr",
    "Algeria": "dz", "Tunisia": "tn", "Mali": "ml", "Ivory Coast": "ci",
    "New Zealand": "nz", "Qatar": "qa", "Indonesia": "id", "Cuba": "cu",
    "Bolivia": "bo", "Panama": "pa", "Honduras": "hn", "Costa Rica": "cr",
    "El Salvador": "sv", "Guatemala": "gt", "Jamaica": "jm", "Paraguay": "py",
    "United Arab Emirates": "ae", "Russia": "ru", "China": "cn",
    "India": "in", "Pakistan": "pk", "Nepal": "np", "Sri Lanka": "lk",
    "Kenya": "ke", "Ethiopia": "et", "Zimbabwe": "zw", "Zambia": "zm",
    "Concaf": "us",  # fallback
}

def get_flag(team): return FLAG_MAP.get(team, "🏴")

def load_wc_history():
    if os.path.exists(WC_HISTORY_FILE):
        try:
            with open(WC_HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def save_wc_history(history):
    if not os.path.exists("data"): os.makedirs("data")
    with open(WC_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def fetch_matches(status_filter=None, date_from=None, date_to=None):
    """Fetch from ALL competitions, not just WC."""
    url = "https://api.football-data.org/v4/matches?"
    if status_filter: url += f"status={status_filter}&"
    if date_from: url += f"dateFrom={date_from}&dateTo={date_to or date_from}&"
    try:
        r = requests.get(url, headers=HEADERS_FOOTBALL, timeout=10)
        if r.status_code == 200: return r.json().get("matches", [])
        print(f"  [API] Status {r.status_code}: {r.text[:200]}")
    except Exception as e: print(f"  [API Error] {e}")
    return []

def generate_score_html(home, away, home_sc, away_sc, status, minute, stage, competition_name="Football"):
    home_flag_path = get_flag_path(home)
    away_flag_path = get_flag_path(away)
    # Use PNG img tag if path found, otherwise fallback to team initials
    home_flag_html = f'<img src="file:///{home_flag_path}" alt="{home}" class="flag-img">' if home_flag_path else f'<div class="flag-txt">{home[:3].upper()}</div>'
    away_flag_html = f'<img src="file:///{away_flag_path}" alt="{away}" class="flag-img">' if away_flag_path else f'<div class="flag-txt">{away[:3].upper()}</div>'
    is_live = status in ("IN_PLAY", "PAUSED", "HALFTIME")
    is_ft = status == "FINISHED"

    if is_live:
        if status == "HALFTIME":
            badge = "&#9208; HALF TIME"; badge_color = "#ff9f0a"; badge_bg = "rgba(255,159,10,0.15)"
        else:
            badge = "&#128308; LIVE"; badge_color = "#ff3b30"; badge_bg = "rgba(255,59,48,0.15)"
        score_display = f"{home_sc} &mdash; {away_sc}"
        score_color = "#ffffff"
        minute_html = f'<div class="min-badge">{minute}\u2019</div>' if minute else ""
    elif is_ft:
        badge = "&#9989; FULL TIME"; badge_color = "#30d158"; badge_bg = "rgba(48,209,88,0.15)"
        score_display = f"{home_sc} &mdash; {away_sc}"
        score_color = "#ffffff"
        minute_html = '<div class="min-badge">FT</div>'
    else:
        badge = "&#9201; UPCOMING"; badge_color = "#0a84ff"; badge_bg = "rgba(10,132,255,0.15)"
        score_display = "? &mdash; ?"
        score_color = "#555"
        minute_html = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800;900&display=swap" rel="stylesheet">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    width: 1080px; height: 1080px;
    font-family: 'Inter', sans-serif;
    background: radial-gradient(ellipse at 20% 20%, #061a0a 0%, #010a03 50%, #000 100%);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    overflow: hidden; position: relative;
}}
.glow1 {{ position:absolute; width:500px; height:500px; border-radius:50%;
    background: radial-gradient(circle, rgba(0,200,70,0.07) 0%, transparent 70%);
    top:-100px; left:-100px; }}
.glow2 {{ position:absolute; width:500px; height:500px; border-radius:50%;
    background: radial-gradient(circle, rgba(255,200,0,0.05) 0%, transparent 70%);
    bottom:-100px; right:-100px; }}
.card {{
    position:relative; z-index:2; width:960px;
    background: rgba(10,18,12,0.9);
    backdrop-filter: blur(40px) saturate(180%);
    -webkit-backdrop-filter: blur(40px) saturate(180%);
    border: 1px solid rgba(255,255,255,0.08);
    border-top: 2px solid rgba(0,200,70,0.5);
    border-radius: 40px;
    padding: 55px 65px 45px;
    box-shadow: 0 40px 100px rgba(0,0,0,0.8), 0 0 60px rgba(0,180,60,0.06);
    display: flex; flex-direction: column; align-items: center; gap: 35px;
}}
.top-row {{ display:flex; justify-content:space-between; align-items:center; width:100%; }}
.wc-badge {{
    background: linear-gradient(135deg, rgba(212,175,55,0.2), rgba(212,175,55,0.04));
    border: 1px solid rgba(212,175,55,0.5); border-radius: 100px;
    padding: 10px 22px; font-size: 18px; font-weight: 700; color: #d4af37;
    letter-spacing: 1px; text-transform: uppercase;
}}
.status-badge {{
    background: {badge_bg}; border: 1.5px solid {badge_color};
    border-radius: 100px; padding: 10px 22px;
    font-size: 20px; font-weight: 800; color: {badge_color}; letter-spacing: 1px;
}}
.stage {{ font-size: 17px; font-weight: 600; color: rgba(255,255,255,0.35);
    text-transform: uppercase; letter-spacing: 1.5px; }}
.scoreboard {{ display:flex; align-items:center; justify-content:space-between;
    width:100%; gap: 10px; }}
.team {{ display:flex; flex-direction:column; align-items:center; gap:18px; flex:1; }}
.flag-img {{ width:130px; height:auto; object-fit:contain;
    filter: drop-shadow(0 8px 20px rgba(0,0,0,0.7)); border-radius: 6px; }}
.flag-txt {{ width:130px; height:86px; border-radius:8px;
    background:rgba(255,255,255,0.1); border:2px solid rgba(255,255,255,0.2);
    display:flex;align-items:center;justify-content:center;
    font-size:32px;font-weight:900;color:rgba(255,255,255,0.6); }}
.tname {{ font-size: 30px; font-weight: 800; color:#fff; text-align:center; }}
.score-mid {{ display:flex; flex-direction:column; align-items:center; gap:10px; }}
.score {{ font-size: 110px; font-weight: 900; color:{score_color};
    letter-spacing: -4px; line-height: 1;
    text-shadow: 0 0 60px rgba(255,255,255,0.08); }}
.min-badge {{ background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.12);
    border-radius:100px; padding:8px 22px; font-size:20px; font-weight:700;
    color:rgba(255,255,255,0.6); }}
.sep {{ width:100%; height:1px;
    background: linear-gradient(90deg, transparent, rgba(0,200,70,0.35), transparent); }}
.footer {{ display:flex; justify-content:space-between; align-items:center; width:100%; }}
.brand {{ font-size:18px; font-weight:800; color:rgba(255,255,255,0.45);
    letter-spacing:3px; text-transform:uppercase; }}
.brand span {{ color:#ff3b30; }}
.hashtag {{ font-size:17px; font-weight:700; color:rgba(212,175,55,0.6); }}
</style>
</head>
<body>
<div class="glow1"></div>
<div class="glow2"></div>
<div class="card">
    <div class="top-row">
        <div class="wc-badge">&#127942; {competition_name}</div>
        <div class="status-badge">{badge}</div>
    </div>
    <div class="stage">{stage}</div>
    <div class="scoreboard">
        <div class="team">
            {home_flag_html}
            <div class="tname">{home}</div>
        </div>
        <div class="score-mid">
            <div class="score">{score_display}</div>
            {minute_html}
        </div>
        <div class="team">
            {away_flag_html}
            <div class="tname">{away}</div>
        </div>
    </div>
    <div class="sep"></div>
    <div class="footer">
        <div class="brand">NEPAL CENTRAL <span>NEWS</span></div>
        <div class="hashtag">&#9917; #WorldCup2026</div>
    </div>
</div>
</body>
</html>"""

def build_caption(home, away, home_sc, away_sc, status, minute, stage, competition_name="Football"):
    hf, af = get_flag(home), get_flag(away)
    comp_label = competition_name
    if status in ("IN_PLAY", "PAUSED"):
        return f"""LIVE UPDATE | {comp_label}

{hf} {home} {home_sc} - {away_sc} {away} {af}
Minute: {minute}' | Stage: {stage}

The action is live! Follow Nepal Central News for real-time updates throughout the match.

#Football #{competition_name.replace(' ','')} #{home.replace(' ','')} #{away.replace(' ','')}"""
    elif status == "HALFTIME":
        return f"""HALF TIME | {comp_label}

{hf} {home} {home_sc} - {away_sc} {away} {af}
Stage: {stage}

The referee has blown the whistle for half time! Nepal Central News keeps you updated live.

#Football #HalfTime #{competition_name.replace(' ','')} #{home.replace(' ','')} #{away.replace(' ','')}"""
    elif status == "FINISHED":
        if home_sc > away_sc: result = f"{home} WIN!"
        elif away_sc > home_sc: result = f"{away} WIN!"
        else: result = "IT'S A DRAW!"
        return f"""FULL TIME | {comp_label}

{hf} {home} {home_sc} - {away_sc} {away} {af}
RESULT: {result} | Stage: {stage}

That's the final whistle! Nepal Central News brings you the complete result.

#Football #FullTime #{competition_name.replace(' ','')} #{home.replace(' ','')} #{away.replace(' ','')}"""
    return ""

def get_page_access_token():
    if not FB_PAGE_ACCESS_TOKEN or not FB_PAGE_ID: return None
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}?fields=access_token&access_token={FB_PAGE_ACCESS_TOKEN}"
    try:
        r = requests.get(url, timeout=10); data = r.json()
        if 'access_token' in data: return data['access_token']
        print(f"    [FB Token Error] {data}")
    except Exception as e: print(f"    [FB Exception] {e}")
    return None

def upload_to_facebook(image_path, caption):
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        print("    [!] FB Credentials missing."); return False
    token = get_page_access_token()
    if not token: print("    [!] No page token."); return False
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/photos"
    try:
        with open(image_path, 'rb') as f:
            r = requests.post(url, data={'message': caption, 'access_token': token}, files={'source': f}, timeout=30)
        if r.status_code == 200: print("    [OK] Posted to Facebook!"); return True
        else: print(f"    [FB Error] {r.text}"); return False
    except Exception as e: print(f"    [FB Exception] {e}"); return False

def run_wc_bot():
    print("\n[WC BOT] FIFA World Cup 2026 Score Bot Starting...")
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    if not os.path.exists(POSTED_DIR): os.makedirs(POSTED_DIR)

    hti = Html2Image(size=(1080, 1080), browser_executable='google-chrome')
    hti.output_path = OUTPUT_DIR
    hti.browser.flags = ['--no-sandbox', '--disable-setuid-sandbox', '--allow-file-access-from-files']

    history = load_wc_history()
    posted_any = False
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Check LIVE matches
    print("\n[->] Checking LIVE matches...")
    for match in fetch_matches(status_filter="IN_PLAY,PAUSED,HALFTIME"):
        home = match['homeTeam']['name']
        away = match['awayTeam']['name']
        home_sc = match['score']['fullTime']['home'] or 0
        away_sc = match['score']['fullTime']['away'] or 0
        status = match['status']
        minute = match.get('minute')
        stage = match.get('stage', 'Group Stage').replace('_', ' ').title()
        competition_name = match.get('competition', {}).get('name', 'Football')
        mid = str(match['id'])
        key = f"{mid}_{home_sc}_{away_sc}_{status}"
        if history.get(mid) == key: print(f"  [Skip] {home} vs {away} unchanged."); continue
        print(f"  [LIVE] [{competition_name}] {home} {home_sc}-{away_sc} {away}")
        html = generate_score_html(home, away, home_sc, away_sc, status, minute, stage, competition_name)
        caption = build_caption(home, away, home_sc, away_sc, status, minute, stage, competition_name)
        fname = f"wc_live_{mid}.png"
        hti.screenshot(html_str=html, save_as=fname)
        upload_to_facebook(os.path.join(OUTPUT_DIR, fname), caption)
        history[mid] = key
        posted_any = True
        time.sleep(3)

    # Check FINISHED matches today
    print("\n[->] Checking FINISHED matches today...")
    for match in fetch_matches(status_filter="FINISHED", date_from=today, date_to=today):
        home = match['homeTeam']['name']
        away = match['awayTeam']['name']
        home_sc = match['score']['fullTime']['home']
        away_sc = match['score']['fullTime']['away']
        stage = match.get('stage', 'Group Stage').replace('_', ' ').title()
        competition_name = match.get('competition', {}).get('name', 'Football')
        mid = str(match['id'])
        ft_key = f"{mid}_FT_{home_sc}_{away_sc}"
        if history.get(mid + "_ft") == ft_key: print(f"  [Skip] {home} vs {away} FT already posted."); continue
        print(f"  [FT] [{competition_name}] {home} {home_sc}-{away_sc} {away}")
        html = generate_score_html(home, away, home_sc, away_sc, "FINISHED", None, stage, competition_name)
        caption = build_caption(home, away, home_sc, away_sc, "FINISHED", None, stage, competition_name)
        fname = f"wc_ft_{mid}.png"
        hti.screenshot(html_str=html, save_as=fname)
        upload_to_facebook(os.path.join(OUTPUT_DIR, fname), caption)
        history[mid + "_ft"] = ft_key
        posted_any = True
        time.sleep(3)

    if not posted_any:
        print("\n[--] Nothing new to post. All scores up to date!")
    save_wc_history(history)
    print("\n[WC BOT] Done!")

if __name__ == "__main__":
    run_wc_bot()
