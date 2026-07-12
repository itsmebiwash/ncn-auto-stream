import time
import requests
from database.db_client import get_db
from config.settings import FB_PAGE_ID, FB_ACCESS_TOKEN
from datetime import datetime, timezone, timedelta

def get_post_insights(fb_post_id):
    if not FB_ACCESS_TOKEN:
        return None
    url = f"https://graph.facebook.com/v21.0/{fb_post_id}/insights"
    params = {
        'metric': 'post_impressions,post_engagements',
        'access_token': FB_ACCESS_TOKEN
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        metrics = {}
        for item in data.get('data', []):
            name = item.get('name')
            # Extract the total value
            if item.get('values'):
                val = item['values'][0].get('value', 0)
                metrics[name] = val
        return metrics
    except Exception as e:
        print(f"[Insights Error] {e}")
        return None

def analyze_engagement_and_update_weights():
    print("Starting Engagement Analysis...")
    db = get_db()
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    # This is a basic fallback for SQLite find
    try:
        results = db.articles.find({"status": "posted", "posted_at": {"$gte": cutoff}})
    except:
        results = []
        cursor = db.articles.conn.execute("SELECT data FROM articles")
        for row in cursor.fetchall():
            import json
            data = json.loads(row[0])
            if data.get("status") == "posted" and data.get("posted_at") >= cutoff.isoformat():
                results.append(data)
                
    total_engagements = 0
    count = 0
    
    keyword_stats = {}
    
    for article in results:
        fb_post_id = article.get("facebook_post_id")
        if not fb_post_id:
            continue
            
        metrics = get_post_insights(fb_post_id)
        if metrics:
            engagements = metrics.get('post_engagements', 0)
            total_engagements += engagements
            count += 1
            
            # Record engagements per keyword
            for kw in article.get("pexels_search_keywords", []):
                if kw not in keyword_stats:
                    keyword_stats[kw] = []
                keyword_stats[kw].append(engagements)
                
            time.sleep(2) # Avoid aggressive rate limits
            
    if count == 0:
        print("No recent posts to analyze.")
        return
        
    baseline = total_engagements / count
    print(f"Baseline engagement per post: {baseline:.2f}")
    
    # Identify high performing keywords (> 50% above baseline)
    for kw, eng_list in keyword_stats.items():
        avg_eng = sum(eng_list) / len(eng_list)
        if avg_eng > (baseline * 1.5):
            print(f"Viral Keyword Detected: '{kw}' (Avg Eng: {avg_eng:.2f})")
            
            # Save to config collection for future use in priority scoring
            try:
                db.config.update_one(
                    {"type": "keyword_weight", "keyword": kw},
                    {"$set": {"weight": 2.0, "updated_at": datetime.now(timezone.utc)}},
                    upsert=True
                )
            except:
                print("Could not update keyword weight in database.")

if __name__ == "__main__":
    analyze_engagement_and_update_weights()
