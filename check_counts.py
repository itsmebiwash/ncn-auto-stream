from database.db_client import get_db
from datetime import datetime, timezone, timedelta

db = get_db()
cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

print("Status Counts (Last 24h):")
for status in ['text_scored', 'queued', 'processing', 'posted', 'failed', 'scraped', 'filtered_out']:
    count = db.articles.count_documents({"status": status, "created_at": {"$gte": cutoff}})
    print(f"  {status}: {count}")
    
text_scored = list(db.articles.find({"status": "text_scored"}))
if text_scored:
    print("\nText Scored Articles:")
    for a in text_scored:
        print(f"- {a.get('source_name')}")
