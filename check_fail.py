from database.db_client import get_db

db = get_db()
failed = list(db.articles.find({'status': 'failed'}).sort('updated_at', -1).limit(5))
for a in failed:
    print(f"Failed Article: {a.get('original_title')}")
    print(f"Fail Reason: {a.get('fail_reason', 'No reason specified')}")
    print("---")
