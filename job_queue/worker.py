import os
import time
from datetime import datetime, timezone
from pymongo import ReturnDocument
from database.db_client import get_db


def poll_queue():
    """
    Atomically claims the single highest-priority queued article.
    Used by the legacy worker and any ad-hoc callers.
    Returns the article dict (status='processing') or None.
    """
    db = get_db()
    try:
        article = db.articles.find_one_and_update(
            {"status": "queued"},
            {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}},
            sort=[("priority_score", -1), ("created_at", -1)],
            return_document=ReturnDocument.AFTER
        )
        return article
    except Exception as e:
        print(f"[Queue Error] {e}")
        return None
