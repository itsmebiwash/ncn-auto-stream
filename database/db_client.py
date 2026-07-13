import os
import time
import sqlite3
import json
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError, ServerSelectionTimeoutError
from config.settings import MONGO_URL

# ── Connection State ──────────────────────────────────────────────────────────
_mongo_client   = None   # the MongoClient (reused across calls)
_db_instance    = None   # the actual database (MongoDB or SQLite)
_last_failed_at = 0.0    # timestamp of last failed MongoDB attempt
_RETRY_INTERVAL = 60.0   # retry MongoDB after this many seconds of failure


class SQLiteFallbackCollection:
    def __init__(self, db_conn, table_name):
        self.conn = db_conn
        self.table_name = table_name
        self.conn.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT
            )
        ''')
        self.conn.commit()

    def insert_one(self, document):
        doc_copy = dict(document)
        if "_id" in doc_copy:
            doc_copy["_id"] = str(doc_copy["_id"])
        for k, v in doc_copy.items():
            if isinstance(v, datetime):
                doc_copy[k] = v.isoformat()
        self.conn.execute(
            f"INSERT INTO {self.table_name} (data) VALUES (?)",
            (json.dumps(doc_copy),)
        )
        self.conn.commit()
        class Result:
            inserted_id = 1
        return Result()

    def find_one(self, query=None):
        cursor = self.conn.execute(f"SELECT data FROM {self.table_name}")
        rows = cursor.fetchall()
        for row in rows:
            data = json.loads(row[0])
            match = True
            for k, v in (query or {}).items():
                if k not in data:
                    match = False; break
                if isinstance(v, dict):
                    if "$gte" in v:
                        cmp = v["$gte"].isoformat() if isinstance(v["$gte"], datetime) else v["$gte"]
                        if data[k] < cmp:
                            match = False; break
                elif data[k] != v:
                    match = False; break
            if match:
                return data
        return None

    def find(self, query=None, sort=None, limit=0):
        cursor = self.conn.execute(f"SELECT data FROM {self.table_name}")
        rows   = cursor.fetchall()
        result = [json.loads(r[0]) for r in rows]
        return result[:limit] if limit else result

    def find_one_and_update(self, query, update, sort=None, return_document=None):
        cursor = self.conn.execute(f"SELECT id, data FROM {self.table_name}")
        rows   = cursor.fetchall()
        for row in rows:
            row_id = row[0]
            data   = json.loads(row[1])
            match  = True
            for k, v in (query or {}).items():
                if k not in data or data[k] != v:
                    match = False; break
            if match:
                set_data = update.get("$set", {})
                for k, v in set_data.items():
                    data[k] = v.isoformat() if isinstance(v, datetime) else v
                self.conn.execute(
                    f"UPDATE {self.table_name} SET data = ? WHERE id = ?",
                    (json.dumps(data), row_id)
                )
                self.conn.commit()
                return data
        return None

    def update_one(self, query, update, **kwargs):
        self.find_one_and_update(query, update)

    def update_many(self, query, update, **kwargs):
        cursor = self.conn.execute(f"SELECT id, data FROM {self.table_name}")
        for row in cursor.fetchall():
            row_id = row[0]
            data   = json.loads(row[1])
            match  = all(data.get(k) == v for k, v in (query or {}).items())
            if match:
                for k, v in update.get("$set", {}).items():
                    data[k] = v.isoformat() if isinstance(v, datetime) else v
                for k in update.get("$unset", {}):
                    data.pop(k, None)
                self.conn.execute(
                    f"UPDATE {self.table_name} SET data = ? WHERE id = ?",
                    (json.dumps(data), row_id)
                )
        self.conn.commit()

    def count_documents(self, query=None):
        return 0

    def create_index(self, keys, **kwargs):
        pass


class SQLiteFallbackDB:
    def __init__(self):
        self.conn     = sqlite3.connect('local_fallback.db', check_same_thread=False)
        self.articles = SQLiteFallbackCollection(self.conn, 'articles')
        self.telemetry = SQLiteFallbackCollection(self.conn, 'telemetry')


def _try_connect_mongo():
    """Attempt a fresh MongoDB connection. Returns (client, db) or raises."""
    client = MongoClient(
        MONGO_URL,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
        retryWrites=True,
    )
    client.admin.command('ping')
    return client, client.news_engine


def get_db():
    """
    Always tries MongoDB first.
    If MongoDB was recently unavailable, waits _RETRY_INTERVAL seconds
    before retrying so we don't spam connection attempts, but we NEVER
    permanently cache a SQLite fallback — we always try to reconnect.
    """
    global _mongo_client, _db_instance, _last_failed_at

    # If we already have a working MongoDB connection, return it immediately.
    if _db_instance is not None and not isinstance(_db_instance, SQLiteFallbackDB):
        try:
            _mongo_client.admin.command('ping')   # quick liveness check
            return _db_instance
        except Exception:
            # Connection dropped — clear the cached instance so we retry below.
            _mongo_client   = None
            _db_instance    = None
            _last_failed_at = 0.0   # force immediate retry

    if not MONGO_URL:
        print("WARNING: MONGO_URL is not set. Using SQLite Fallback Database.")
        if _db_instance is None:
            _db_instance = SQLiteFallbackDB()
        return _db_instance

    # Rate-limit retry attempts
    now = time.time()
    if _last_failed_at and (now - _last_failed_at) < _RETRY_INTERVAL:
        # Still in cool-down — use SQLite temporarily (no permanent cache)
        print(f"[DB] MongoDB unavailable. Retrying in "
              f"{_RETRY_INTERVAL - (now - _last_failed_at):.0f}s. Using SQLite temporarily.")
        return SQLiteFallbackDB()

    # Try to (re)connect to MongoDB
    try:
        print("[DB] Connecting to MongoDB...")
        _mongo_client, _db_instance = _try_connect_mongo()
        _last_failed_at = 0.0   # reset failure timer on success
        print("[DB] MongoDB connected successfully.")
        return _db_instance
    except Exception as e:
        _last_failed_at = time.time()
        _mongo_client   = None
        _db_instance    = None
        print(f"[DB] MongoDB connection failed: {e}. Using SQLite temporarily.")
        return SQLiteFallbackDB()


def reset_db():
    """Force a fresh connection attempt on next get_db() call."""
    global _mongo_client, _db_instance, _last_failed_at
    _mongo_client   = None
    _db_instance    = None
    _last_failed_at = 0.0


def init_db():
    """Initialize database connection and create indexes if using MongoDB."""
    for attempt in range(3):
        try:
            db = get_db()
            if isinstance(db, SQLiteFallbackDB):
                if attempt < 2:
                    print(f"[DB] MongoDB not ready. Retrying in 5s... (attempt {attempt+1}/3)")
                    time.sleep(5)
                    reset_db()
                    continue
                print("[DB] WARNING: Using SQLite fallback — MongoDB could not be reached.")
                return
            db.articles.create_index("content_hash", unique=True)
            db.articles.create_index("status")
            db.articles.create_index([("priority_score", -1), ("created_at", -1)])
            print("MongoDB initialized and indexes created.")
            return
        except Exception as e:
            print(f"[DB] Failed to initialize: {e}")
            if attempt < 2:
                time.sleep(5)
                reset_db()
