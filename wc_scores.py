# -*- coding: utf-8 -*-
"""
=============================================================================
  NEPAL CENTRAL NEWS — Football Score Bot (All Competitions)
  Runs every 15 minutes via GitHub Actions.
  Posts live scores, half-time, and full-time results to Facebook.
=============================================================================
"""
import requests, time, os, json, shutil
from html2image import Html2Image
from datetime import datetime, timezone, timedelta

# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================
FOOTBALL_API_KEY     = os.environ.get("FOOTBALL_API_KEY", "")
FB_PAGE_ID           = os.environ.get("FB_PAGE_ID", "")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")

NEPAL_TZ_OFFSET  = timedelta(hours=5, minutes=45)
HEADERS_FOOTBALL = {"X-Auth-Token": FOOTBALL_API_KEY}
OUTPUT_DIR       = "wc_output"
POSTED_DIR       = "wc_posted"
WC_HISTORY_FILE  = "data/wc_posted_history.json"
ASSETS_DIR       = os.path.abspath("assets")
FLAGS_DIR        = os.path.join(ASSETS_DIR, "Flag PNG")

# ============================================================
# COUNTRY CODE MAP  (team name → ISO 2-letter code → PNG file)
# ============================================================
COUNTRY_CODE_MAP = {
    "Argentina":"ar","Brazil":"br","France":"fr","Germany":"de","Spain":"es",
    "England":"gb-eng","Portugal":"pt","Netherlands":"nl","Belgium":"be",
    "Italy":"it","Croatia":"hr","Uruguay":"uy","Mexico":"mx",
    "United States":"us","Canada":"ca","Morocco":"ma","Senegal":"sn",
    "Japan":"jp","South Korea":"kr","Australia":"au","Saudi Arabia":"sa",
    "Iran":"ir","Switzerland":"ch","Denmark":"dk","Poland":"pl","Serbia":"rs",
    "Ukraine":"ua","Colombia":"co","Ecuador":"ec","Peru":"pe","Chile":"cl",
    "Venezuela":"ve","Egypt":"eg","Nigeria":"ng","Cameroon":"cm","Ghana":"gh",
    "Norway":"no","Sweden":"se","Turkey":"tr","Austria":"at",
    "Czech Republic":"cz","Hungary":"hu","Slovakia":"sk","Romania":"ro",
    "Scotland":"gb-sct","Wales":"gb-wls","Northern Ireland":"gb-nir",
    "Ireland":"ie","Greece":"gr","Algeria":"dz","Tunisia":"tn","Mali":"ml",
    "Ivory Coast":"ci","New Zealand":"nz","Qatar":"qa","Indonesia":"id",
    "Cuba":"cu","Bolivia":"bo","Panama":"pa","Honduras":"hn","Costa Rica":"cr",
    "El Salvador":"sv","Guatemala":"gt","Jamaica":"jm","Paraguay":"py",
    "United Arab Emirates":"ae","Russia":"ru","China":"cn","India":"in",
    "Pakistan":"pk","Nepal":"np","Sri Lanka":"lk","Kenya":"ke",
    "Ethiopia":"et","Zimbabwe":"zw","Zambia":"zm","Finland":"fi",
    "Slovakia":"sk","Bulgaria":"bg","Belarus":"by","Moldova":"md",
    "Montenegro":"me","Bosnia and Herzegovina":"ba","North Macedonia":"mk",
    "Kosovo":"xk","Albania":"al","Armenia":"am","Azerbaijan":"az",
    "Georgia":"ge","Israel":"il","Cyprus":"cy","Luxembourg":"lu",
    "Malta":"mt","Iceland":"is","Faroe Islands":"fo","Andorra":"ad",
    "Liechtenstein":"li","San Marino":"sm","Gibraltar":"gi",
}

def get_flag_path(team_name):
    """Return abs path to flag PNG or None. Safe — never crashes."""
    try:
        code = COUNTRY_CODE_MAP.get(team_name, "").lower()
        if not code:
            return None
        path = os.path.join(FLAGS_DIR, f"{code}.png")
        if os.path.exists(path):
            return path.replace("\\", "/")
    except Exception:
        pass
    return None

def flag_html(team_name, css_class="flag-img"):
    """Return safe <img> or fallback <div> for a team flag."""
    p = get_flag_path(team_name)
    if p:
        return f'<img src="file:///{p}" alt="{team_name}" class="{css_class}">'
    initials = team_name[:3].upper() if team_name else "?"
    return f'<div class="flag-txt">{initials}</div>'

# ============================================================
# HISTORY (deduplicate posts)
# ============================================================
WC_HISTORY_TXT = "data/wc_posted_history.txt"

def load_wc_history():
    history = {}
    if os.path.exists(WC_HISTORY_TXT):
        try:
            with open(WC_HISTORY_TXT, "r", encoding="utf-8") as f:
                for line in f:
                    if ":::" in line:
                        k, v = line.strip().split(":::", 1)
                        history[k] = v
        except Exception:
            pass
    return history

def save_wc_history(history):
    try:
        if not os.path.exists("data"):
            os.makedirs("data")
        with open(WC_HISTORY_TXT, "w", encoding="utf-8") as f:
            for k, v in history.items():
                f.write(f"{k}:::{v}\n")
    except Exception as e:
        print(f"  [History Save Error] {e}")

# ============================================================
# API FETCH
# ============================================================
def fetch_matches(status_filter=None, date_from=None, date_to=None):
    """Fetch from ALL competitions. Returns [] on any error."""
    if not FOOTBALL_API_KEY:
        print("  [!] FOOTBALL_API_KEY not set.")
        return []
    url = "https://api.football-data.org/v4/matches?"
    if status_filter:
        url += f"status={status_filter}&"
    if date_from:
        url += f"dateFrom={date_from}&dateTo={date_to or date_from}&"
    try:
        r = requests.get(url, headers=HEADERS_FOOTBALL, timeout=15)
        if r.status_code == 200:
            return r.json().get("matches", [])
        print(f"  [API] HTTP {r.status_code}")
    except Exception as e:
        print(f"  [API Error] {e}")
    return []

def get_live_score(match):
    """
    Get the correct current score during a live match.
    football-data.org puts live score in score.fullTime during play,
    but sometimes only in score.halfTime at HT. Handle both safely.
    """
    score = match.get("score", {})
    ft    = score.get("fullTime", {})
    ht    = score.get("halfTime", {})
    status = match.get("status", "")

    h = ft.get("home")
    a = ft.get("away")

    # If fullTime is null during half-time, fallback to halfTime score
    if status == "HALFTIME" and (h is None or a is None):
        h = ht.get("home", 0)
        a = ht.get("away", 0)

    return (h or 0), (a or 0)

# ============================================================
# HTML CARD GENERATOR
# ============================================================
def generate_score_html(home, away, home_sc, away_sc, status, minute, stage, competition_name="Football"):
    home_flag = flag_html(home, "flag-img")
    away_flag = flag_html(away, "flag-img")
    is_live = status in ("IN_PLAY", "PAUSED", "HALFTIME")
    is_ft   = status == "FINISHED"

    if is_live:
        if status == "HALFTIME":
            badge = "&#9208; HALF TIME"; badge_color = "#ff9f0a"; badge_bg = "rgba(255,159,10,0.15)"
        else:
            badge = "&#128308; LIVE"; badge_color = "#ff3b30"; badge_bg = "rgba(255,59,48,0.15)"
        score_display = f"{home_sc} &mdash; {away_sc}"
        score_color   = "#ffffff"
        minute_html   = f'<div class="min-badge">{minute}&#8242;</div>' if minute else ""
    elif is_ft:
        badge = "&#9989; FULL TIME"; badge_color = "#30d158"; badge_bg = "rgba(48,209,88,0.15)"
        score_display = f"{home_sc} &mdash; {away_sc}"
        score_color   = "#ffffff"
        minute_html   = '<div class="min-badge">FT</div>'
    else:
        badge = "&#9201; UPCOMING"; badge_color = "#0a84ff"; badge_bg = "rgba(10,132,255,0.15)"
        score_display = "? &mdash; ?"
        score_color   = "#555"
        minute_html   = ""

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800;900&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1080px;height:1080px;font-family:'Inter',sans-serif;
background:radial-gradient(ellipse at 20% 20%,#061a0a 0%,#010a03 50%,#000 100%);
display:flex;flex-direction:column;align-items:center;justify-content:center;
overflow:hidden;position:relative}}
.glow1{{position:absolute;width:500px;height:500px;border-radius:50%;
background:radial-gradient(circle,rgba(0,200,70,0.07) 0%,transparent 70%);top:-100px;left:-100px}}
.glow2{{position:absolute;width:500px;height:500px;border-radius:50%;
background:radial-gradient(circle,rgba(255,200,0,0.05) 0%,transparent 70%);bottom:-100px;right:-100px}}
.card{{position:relative;z-index:2;width:960px;
background:rgba(10,18,12,0.9);backdrop-filter:blur(40px) saturate(180%);
-webkit-backdrop-filter:blur(40px) saturate(180%);
border:1px solid rgba(255,255,255,0.08);border-top:2px solid rgba(0,200,70,0.5);
border-radius:40px;padding:50px 60px 45px;
box-shadow:0 40px 100px rgba(0,0,0,0.8),0 0 60px rgba(0,180,60,0.06);
display:flex;flex-direction:column;align-items:center;gap:32px}}
.top-row{{display:flex;justify-content:space-between;align-items:center;width:100%}}
.wc-badge{{background:linear-gradient(135deg,rgba(212,175,55,0.2),rgba(212,175,55,0.04));
border:1px solid rgba(212,175,55,0.5);border-radius:100px;padding:10px 22px;
font-size:17px;font-weight:700;color:#d4af37;letter-spacing:1px;text-transform:uppercase}}
.status-badge{{background:{badge_bg};border:1.5px solid {badge_color};
border-radius:100px;padding:10px 22px;font-size:19px;font-weight:800;
color:{badge_color};letter-spacing:1px}}
.stage{{font-size:16px;font-weight:600;color:rgba(255,255,255,0.35);
text-transform:uppercase;letter-spacing:1.5px}}
.scoreboard{{display:flex;align-items:center;justify-content:space-between;width:100%;gap:10px}}
.team{{display:flex;flex-direction:column;align-items:center;gap:16px;flex:1}}
.flag-img{{width:130px;height:auto;object-fit:contain;
filter:drop-shadow(0 8px 20px rgba(0,0,0,0.7));border-radius:6px}}
.flag-txt{{width:130px;height:86px;border-radius:8px;
background:rgba(255,255,255,0.1);border:2px solid rgba(255,255,255,0.2);
display:flex;align-items:center;justify-content:center;
font-size:30px;font-weight:900;color:rgba(255,255,255,0.6)}}
.tname{{font-size:28px;font-weight:800;color:#fff;text-align:center}}
.score-mid{{display:flex;flex-direction:column;align-items:center;gap:10px}}
.score{{font-size:108px;font-weight:900;color:{score_color};
letter-spacing:-4px;line-height:1;text-shadow:0 0 60px rgba(255,255,255,0.08)}}
.min-badge{{background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);
border-radius:100px;padding:8px 22px;font-size:19px;font-weight:700;
color:rgba(255,255,255,0.6)}}
.sep{{width:100%;height:1px;
background:linear-gradient(90deg,transparent,rgba(0,200,70,0.35),transparent)}}
.footer{{display:flex;justify-content:space-between;align-items:center;width:100%}}
.brand{{font-size:17px;font-weight:800;color:rgba(255,255,255,0.45);
letter-spacing:3px;text-transform:uppercase}}
.brand span{{color:#ff3b30}}
.hashtag{{font-size:16px;font-weight:700;color:rgba(212,175,55,0.6)}}
</style></head><body>
<div class="glow1"></div><div class="glow2"></div>
<div class="card">
  <div class="top-row">
    <div class="wc-badge">&#127942; {competition_name}</div>
    <div class="status-badge">{badge}</div>
  </div>
  <div class="stage">{stage}</div>
  <div class="scoreboard">
    <div class="team">{home_flag}<div class="tname">{home}</div></div>
    <div class="score-mid">
      <div class="score">{score_display}</div>
      {minute_html}
    </div>
    <div class="team">{away_flag}<div class="tname">{away}</div></div>
  </div>
  <div class="sep"></div>
  <div class="footer">
    <div class="brand">NEPAL CENTRAL <span>NEWS</span></div>
    <div class="hashtag">&#9917; #Football</div>
  </div>
</div></body></html>"""

# ============================================================
# CAPTION BUILDER (no emoji flags — plain text)
# ============================================================
def build_caption(home, away, home_sc, away_sc, status, minute, stage, competition_name="Football"):
    comp = competition_name
    htag_home = home.replace(' ', '')
    htag_away = away.replace(' ', '')
    htag_comp = comp.replace(' ', '')

    if status in ("IN_PLAY", "PAUSED"):
        return (
            f"LIVE UPDATE | {comp}\n\n"
            f"{home} {home_sc} - {away_sc} {away}\n"
            f"Minute: {minute}' | Round: {stage}\n\n"
            f"The action is live! Follow Nepal Central News for real-time updates.\n\n"
            f"#Football #{htag_comp} #{htag_home} #{htag_away}"
        )
    elif status == "HALFTIME":
        return (
            f"HALF TIME | {comp}\n\n"
            f"{home} {home_sc} - {away_sc} {away}\n"
            f"Round: {stage}\n\n"
            f"Half time whistle blown! Second half action coming up. "
            f"Follow Nepal Central News for live updates.\n\n"
            f"#Football #HalfTime #{htag_comp} #{htag_home} #{htag_away}"
        )
    elif status == "FINISHED":
        if home_sc > away_sc:
            result = f"{home} WIN!"
        elif away_sc > home_sc:
            result = f"{away} WIN!"
        else:
            result = "IT'S A DRAW!"
        return (
            f"FULL TIME | {comp}\n\n"
            f"{home} {home_sc} - {away_sc} {away}\n"
            f"RESULT: {result} | Round: {stage}\n\n"
            f"Final whistle! Nepal Central News brings you the complete result.\n\n"
            f"#Football #FullTime #{htag_comp} #{htag_home} #{htag_away}"
        )
    return ""

# ============================================================
# FACEBOOK POSTING
# ============================================================
def get_page_token():
    if not FB_PAGE_ACCESS_TOKEN or not FB_PAGE_ID:
        return None
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}?fields=access_token&access_token={FB_PAGE_ACCESS_TOKEN}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        if "access_token" in data:
            return data["access_token"]
        print(f"    [FB Token Error] {data.get('error', {}).get('message', data)}")
    except Exception as e:
        print(f"    [FB Token Exception] {e}")
    return None

def upload_to_facebook(image_path, caption):
    """Upload image + caption to Facebook. Returns True on success."""
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        print("    [!] FB credentials not set."); return False
    if not os.path.exists(image_path):
        print(f"    [!] Image file not found: {image_path}"); return False
    if os.path.getsize(image_path) < 5000:
        print(f"    [!] Image too small (likely blank): {image_path}"); return False

    token = get_page_token()
    if not token:
        print("    [!] Could not get Page Access Token."); return False

    try:
        with open(image_path, "rb") as f:
            r = requests.post(
                f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/photos",
                data={"message": caption, "access_token": token},
                files={"source": f},
                timeout=60,
            )
        if r.status_code == 200:
            print("    [OK] Posted to Facebook!")
            return True
        err = r.json().get("error", {})
        print(f"    [FB Error {r.status_code}] {err.get('message', r.text[:200])}")
        return False
    except Exception as e:
        print(f"    [FB Upload Exception] {e}")
        return False

# ============================================================
# CORE PROCESSOR — one pass of live + finished matches
# ============================================================
def process_matches(hti, history):
    """Single pass: check live + finished matches and post. Returns True if anything was posted."""
    posted_any = False
    now_utc    = datetime.now(timezone.utc)
    today      = now_utc.strftime("%Y-%m-%d")

    # ── 1. LIVE MATCHES ──────────────────────────────────────
    print("\n[->] Checking LIVE matches...")
    live_matches = fetch_matches(status_filter="IN_PLAY,PAUSED,HALFTIME")

    for match in live_matches:
        try:
            home    = match["homeTeam"]["name"]
            away    = match["awayTeam"]["name"]
            status  = match["status"]
            minute  = match.get("minute") or match.get("currentPeriod", "")
            stage   = match.get("stage", "Group Stage").replace("_", " ").title()
            comp    = match.get("competition", {}).get("name", "Football")
            mid     = str(match["id"])

            home_sc, away_sc = get_live_score(match)

            # Key changes every time score OR status changes -> triggers a new post
            key = f"{mid}_{home_sc}_{away_sc}_{status}"
            if history.get(f"live_{mid}") == key:
                print(f"  [Skip] {home} vs {away} - no change ({home_sc}-{away_sc} {status})"); continue

            print(f"  [LIVE] [{comp}] {home} {home_sc}-{away_sc} {away} ({status} {minute})")

            html     = generate_score_html(home, away, home_sc, away_sc, status, minute, stage, comp)
            caption  = build_caption(home, away, home_sc, away_sc, status, minute, stage, comp)
            fname    = f"live_{mid}.png"
            img_path = os.path.join(OUTPUT_DIR, fname)

            hti.screenshot(html_str=html, save_as=fname)
            time.sleep(2)

            if upload_to_facebook(img_path, caption):
                history[f"live_{mid}"] = key
                posted_any = True
                try:
                    shutil.move(img_path, os.path.join(POSTED_DIR, fname))
                except Exception:
                    pass
            time.sleep(3)

        except Exception as e:
            print(f"  [Match Error] {e}")

    # ── 2. FINISHED MATCHES (today only) ────────────────────
    print("\n[->] Checking FINISHED matches today...")
    finished_matches = fetch_matches(status_filter="FINISHED", date_from=today, date_to=today)

    for match in finished_matches:
        try:
            home    = match["homeTeam"]["name"]
            away    = match["awayTeam"]["name"]
            stage   = match.get("stage", "Group Stage").replace("_", " ").title()
            comp    = match.get("competition", {}).get("name", "Football")
            mid     = str(match["id"])

            score   = match.get("score", {}).get("fullTime", {})
            home_sc = score.get("home")
            away_sc = score.get("away")

            if home_sc is None or away_sc is None:
                print(f"  [Skip] {home} vs {away} - score data missing."); continue

            ft_key = f"{mid}_FT_{home_sc}_{away_sc}"
            if history.get(f"ft_{mid}") == ft_key:
                print(f"  [Skip] {home} vs {away} FT already posted."); continue

            # Skip very old results unless we've never seen this match at all
            utc_date = match.get("utcDate", "")
            if utc_date:
                try:
                    match_dt  = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
                    hours_ago = (now_utc - match_dt).total_seconds() / 3600
                    if hours_ago > 6:
                        if any(f"live_{mid}" in k or f"ft_{mid}" in k for k in history):
                            print(f"  [Skip] {home} vs {away} - old result, already handled.")
                            continue
                except Exception:
                    pass

            print(f"  [FT] [{comp}] {home} {home_sc}-{away_sc} {away}")

            html     = generate_score_html(home, away, home_sc, away_sc, "FINISHED", None, stage, comp)
            caption  = build_caption(home, away, home_sc, away_sc, "FINISHED", None, stage, comp)
            fname    = f"ft_{mid}.png"
            img_path = os.path.join(OUTPUT_DIR, fname)

            hti.screenshot(html_str=html, save_as=fname)
            time.sleep(2)

            if upload_to_facebook(img_path, caption):
                history[f"ft_{mid}"] = ft_key
                posted_any = True
                try:
                    shutil.move(img_path, os.path.join(POSTED_DIR, fname))
                except Exception:
                    pass
            time.sleep(3)

        except Exception as e:
            print(f"  [Match Error] {e}")

    return posted_any, len(live_matches)


# ============================================================
# MAIN BOT LOGIC — with internal live-polling loop
# ============================================================
def run_wc_bot():
    print("\n[SCORE BOT] Starting - All Competitions")

    if not FOOTBALL_API_KEY:
        print("[!] FOOTBALL_API_KEY not set. Exiting."); return

    for d in [OUTPUT_DIR, POSTED_DIR, "data"]:
        if not os.path.exists(d):
            os.makedirs(d)

    termux_chrome = "/data/data/com.termux/files/usr/bin/chromium-browser"
    win_chrome    = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    win_chrome2   = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    
    if os.path.exists(termux_chrome):
        chrome_path = termux_chrome
    elif os.path.exists(win_chrome):
        chrome_path = win_chrome
    elif os.path.exists(win_chrome2):
        chrome_path = win_chrome2
    else:
        chrome_path = "google-chrome"  # Linux/GitHub Actions fallback
    
    hti = Html2Image(size=(1080, 1080), browser_executable=chrome_path)
    hti.output_path = OUTPUT_DIR
    hti.browser.flags = ["--no-sandbox", "--disable-setuid-sandbox",
                         "--allow-file-access-from-files", "--disable-dev-shm-usage"]

    history = load_wc_history()

    # ─── FIRST PASS ────────────────────────────────────────────
    posted_any, live_count = process_matches(hti, history)
    save_wc_history(history)

    # ─── LIVE POLLING LOOP ─────────────────────────────────────
    # If live matches exist, keep polling every 5 min for up to 110 min
    # This catches every goal/status change in near real-time regardless
    # of how often GitHub Actions triggers (every 30 min).
    if live_count > 0:
        POLL_INTERVAL_SEC = 5 * 60   # 5 minutes
        MAX_LIVE_DURATION = 110 * 60 # 110 minutes max loop time (full match + buffer)
        elapsed = 0

        print(f"\n[LOOP] {live_count} live match(es) detected. Polling every 5 min for up to 110 min...")

        while elapsed < MAX_LIVE_DURATION:
            time.sleep(POLL_INTERVAL_SEC)
            elapsed += POLL_INTERVAL_SEC

            print(f"\n[POLL] +{elapsed//60}m - re-checking matches...")
            history = load_wc_history()  # reload in case other runs saved state
            _, current_live = process_matches(hti, history)
            save_wc_history(history)

            if current_live == 0:
                print("[LOOP] No more live matches. Exiting loop.")
                break

    if not posted_any:
        print("\n[--] Nothing new to post.")

    print("\n[SCORE BOT] Done!")


if __name__ == "__main__":
    run_wc_bot()
