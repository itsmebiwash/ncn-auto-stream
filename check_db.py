from database.db_client import get_db
from datetime import datetime, timezone, timedelta

db = get_db()
cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

print("Recent articles in the last 24 hours:")
recent = list(db.articles.find({"created_at": {"$gte": cutoff}}).sort("created_at", -1))
if not recent:
    print("No articles found in the last 24 hours!")
else:
    for a in recent:
        print(f"[{a.get('created_at')}] {a.get('source_name')}: {str(a.get('original_title'))[:40]} - Status: {a.get('status')}")

print("\nLast 5 articles overall:")
latest = db.articles.find().sort("created_at", -1).limit(5)
for a in latest:
    print(f"[{a.get('created_at')}] {a.get('source_name')}: {str(a.get('original_title'))[:40]} - Status: {a.get('status')}")
