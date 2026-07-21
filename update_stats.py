import os
from database.db_client import get_db
from datetime import datetime, timezone

def generate_posting_report():
    print("[Stats] Generating posting report...")
    db = get_db()
    
    # 1. Get stats for GitHub posts
    github_posts = list(db.articles.find({'status': 'posted', 'posted_from': 'github'}).sort('posted_at', 1))
    gh_count = len(github_posts)
    gh_first = github_posts[0]['posted_at'].strftime('%Y-%m-%d %H:%M:%S UTC') if gh_count > 0 else "N/A"
    gh_last = github_posts[-1]['posted_at'].strftime('%Y-%m-%d %H:%M:%S UTC') if gh_count > 0 else "N/A"
    
    # 2. Get stats for Local posts
    local_posts = list(db.articles.find({'status': 'posted', 'posted_from': {'$ne': 'github'}}).sort('posted_at', 1))
    local_count = len(local_posts)
    local_first = local_posts[0]['posted_at'].strftime('%Y-%m-%d %H:%M:%S UTC') if local_count > 0 else "N/A"
    local_last = local_posts[-1]['posted_at'].strftime('%Y-%m-%d %H:%M:%S UTC') if local_count > 0 else "N/A"

    total = gh_count + local_count

    report_text = f"""======================================
FACEBOOK POSTING STATS (Live)
Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
======================================

Total Posts Ever Published: {total}

From GitHub Actions: {gh_count} posts
  First post: {gh_first}
  Last post:  {gh_last}

From Local (Laptop): {local_count} posts
  First post: {local_first}
  Last post:  {local_last}
======================================
"""

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'posting_stats.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    print(f"[Stats] Updated {report_path}")

if __name__ == '__main__':
    generate_posting_report()
