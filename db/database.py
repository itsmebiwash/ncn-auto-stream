from pymongo import MongoClient
from config.settings import MONGO_URL

def get_db():
    """
    Returns the MongoDB database instance.
    """
    if not MONGO_URL:
        raise ValueError("MONGO_URL is not set in environment.")
    
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    # Using 'news_engine' as the default database name
    db = client.news_engine
    return db

def init_db():
    """
    Initializes indexes on the MongoDB collections.
    """
    try:
        db = get_db()
        # Create indexes for articles collection
        db.articles.create_index("content_hash", unique=True)
        db.articles.create_index("status")
        db.articles.create_index([("priority_score", -1), ("created_at", -1)])
        print("MongoDB initialized and indexes created.")
    except Exception as e:
        print(f"Failed to initialize MongoDB: {e}")
