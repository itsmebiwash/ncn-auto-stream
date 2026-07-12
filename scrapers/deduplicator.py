import hashlib
from datetime import datetime, timedelta, timezone
from db.database import get_db

def generate_hash(url, title):
    """
    Computes an MD5/SHA-256 hash using URL + raw_nepali_title.
    """
    raw_str = f"{url}||{title}".encode('utf-8')
    return hashlib.sha256(raw_str).hexdigest()

def is_duplicate(content_hash):
    """
    Checks the hash against records from the past 48 hours in MongoDB.
    """
    db = get_db()
    forty_eight_hours_ago = datetime.now(timezone.utc) - timedelta(hours=48)
    
    result = db.articles.find_one({
        "content_hash": content_hash,
        "created_at": {"$gte": forty_eight_hours_ago}
    })
    
    return result is not None
