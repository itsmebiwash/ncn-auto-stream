"""
Reset stuck 'processing' articles back to 'queued' so they can be picked up again.
Also reset any 'queued' articles that have no image path back to 'text_scored' so
they get re-rendered on the next GitHub Actions run.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from database.db_client import get_db
from datetime import datetime, timezone

db = get_db()

# 1. Reset stuck 'processing' -> 'queued'
r1 = db.articles.update_many(
    {'status': 'processing'},
    {'$set': {'status': 'queued', 'updated_at': datetime.now(timezone.utc)}}
)
print(f"Reset {r1.modified_count} stuck 'processing' articles -> 'queued'")

# 2. Reset 'queued' articles with NO image path back to 'text_scored'
r2_a = db.articles.update_many(
    {'status': 'queued', 'final_image_path': {'$exists': False}},
    {'$set': {'status': 'text_scored', 'updated_at': datetime.now(timezone.utc)}}
)
r2_b = db.articles.update_many(
    {'status': 'queued', 'final_image_path': ''},
    {'$set': {'status': 'text_scored', 'updated_at': datetime.now(timezone.utc)}}
)
r2_c = db.articles.update_many(
    {'status': 'queued', 'final_image_path': None},
    {'$set': {'status': 'text_scored', 'updated_at': datetime.now(timezone.utc)}}
)
print(f"Reset {r2_a.modified_count + r2_b.modified_count + r2_c.modified_count} 'queued' articles with no image -> 'text_scored'")

# 3. Show final counts
for status in ['text_scored', 'queued', 'processing', 'posted', 'failed']:
    count = db.articles.count_documents({'status': status})
    print(f"  Total {status}: {count}")
