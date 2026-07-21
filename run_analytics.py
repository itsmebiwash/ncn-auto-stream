import time
from datetime import datetime, timedelta, timezone
from database.db_client import get_db
from facebook.insights import fetch_post_insights

def run_analytics_cycle():
    """
    Checks Facebook engagement for posted articles.
    Calculates Engagement Score and updates keyword weights.
    """
    print("Running Analytics & Telemetry Cycle...")
    db = get_db()
    
    # Fetch posts from the last 48 hours
    forty_eight_hours_ago = datetime.now(timezone.utc) - timedelta(hours=48)
    
    posts = list(db.articles.find({
        "status": "posted",
        "facebook_post_id": {"$exists": True, "$ne": None},
        "created_at": {"$gte": forty_eight_hours_ago}
    }, {"_id": 1, "facebook_post_id": 1, "keywords": 1, "category": 1}))
        
    if not posts:
        print("No recent posts to analyze.")
        return
        
    print(f"Analyzing {len(posts)} posts for engagement metrics...")
    
    total_score = 0
    analyzed_count = 0
    
    # First pass: calculate scores
    post_scores = []
    for post in posts:
        fb_post_id = post.get("facebook_post_id")
        metrics = fetch_post_insights(fb_post_id)
        
        if not metrics:
            time.sleep(1) # rate limit prevention
            continue
            
        # Engagement Score = (impressions * 1) + (clicks * 3) + (shares * 5)
        score = (metrics.get('impressions', 0) * 1) + \
                (metrics.get('clicks', 0) * 3) + \
                (metrics.get('shares', 0) * 5)
                
        # Update article with metrics
        db.articles.update_one(
            {"_id": post["_id"]},
            {"$set": {
                "impressions": metrics.get('impressions', 0),
                "engagement_score": score,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        if score > 0:
            total_score += score
            analyzed_count += 1
            post_scores.append({"post": post, "score": score})
            
        time.sleep(2) # Facebook API rate limit prevention
        
    if analyzed_count == 0:
        print("No valid engagement data found.")
        return
        
    average_score = total_score / analyzed_count
    print(f"Average Engagement Score: {average_score:.2f}")
    
    # Second pass: update keyword weights
    for item in post_scores:
        post = item["post"]
        score = item["score"]
        
        # Calculate adjustment factor. Max increase +0.5, Max decrease -0.2
        ratio = score / average_score if average_score > 0 else 1
        
        if ratio > 1.5:
            adjustment = 0.5
        elif ratio > 1.2:
            adjustment = 0.2
        elif ratio < 0.5:
            adjustment = -0.2
        else:
            adjustment = 0.0 # Average performer, no change
            
        if adjustment == 0.0:
            continue
            
        keywords = post.get("keywords", [])
        category = post.get("category", "General")
        
        for kw in keywords:
            if not kw:
                continue
                
            # Upsert keyword score
            db.keyword_scores.update_one(
                {"keyword": kw},
                {
                    "$inc": {"weight_score": adjustment},
                    "$setOnInsert": {"category": category},
                    "$set": {"last_updated": datetime.now(timezone.utc)}
                },
                upsert=True
            )
            
            # Bound the score between 0.1 and 5.0
            kw_doc = db.keyword_scores.find_one({"keyword": kw})
            if kw_doc and kw_doc.get("weight_score", 1.0) < 0.1:
                db.keyword_scores.update_one({"keyword": kw}, {"$set": {"weight_score": 0.1}})
            elif kw_doc and kw_doc.get("weight_score", 1.0) > 5.0:
                db.keyword_scores.update_one({"keyword": kw}, {"$set": {"weight_score": 5.0}})

    print(f"Analyzed {len(posts)} posts. Telemetry cycle complete.")

if __name__ == "__main__":
    while True:
        try:
            run_analytics_cycle()
        except Exception as e:
            print(f"Analytics error: {e}")
            
        time.sleep(6 * 3600)
