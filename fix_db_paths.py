"""
fix_db_paths.py – one-shot script to reconcile DB final_image_path fields
with actual files in the output/ folder.
Run once: python fix_db_paths.py
"""
import sys, os, logging
sys.stdout.reconfigure(encoding='utf-8')
logging.disable(logging.CRITICAL)

from database.db_client import init_db, get_db
from datetime import datetime, timezone

init_db()
db = get_db()

output_dir = os.path.abspath('output')

# Index every real .jpg currently in output/ (not subfolders)
actual_files = {}
for f in os.listdir(output_dir):
    if f.endswith('.jpg') and os.path.isfile(os.path.join(output_dir, f)):
        actual_files[f] = os.path.join(output_dir, f)

print(f'Real .jpg files in output/: {len(actual_files)}')

# Fetch all queued articles
queued = list(db.articles.find({'status': 'queued'}))
print(f'Queued articles in DB:       {len(queued)}')

matched = 0
missing = 0
now = datetime.now(timezone.utc)

for art in queued:
    slug = art.get('topic_slug', '')
    stored_path = art.get('final_image_path', '')
    stored_basename = os.path.basename(stored_path) if stored_path else ''

    # Priority 1: exact basename match (covers old manually-named files)
    abs_path = None
    if stored_basename and stored_basename in actual_files:
        abs_path = actual_files[stored_basename]

    # Priority 2: slug-based match (new naming convention)
    if not abs_path and slug:
        slug_file = slug + '.jpg'
        if slug_file in actual_files:
            abs_path = actual_files[slug_file]

    if abs_path and os.path.exists(abs_path):
        db.articles.update_one(
            {'_id': art['_id']},
            {'$set': {'final_image_path': abs_path}}
        )
        matched += 1
    else:
        # File is truly missing – mark failed so pipeline skips it
        db.articles.update_one(
            {'_id': art['_id']},
            {'$set': {'status': 'failed', 'fail_reason': 'image_file_missing', 'updated_at': now}}
        )
        missing += 1

print(f'Matched with real file:  {matched}')
print(f'Marked failed (no file): {missing}')
print(f'Remaining queued:        {db.articles.count_documents({"status": "queued"})}')
