import os
import sqlite3
import json
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError
from config.settings import MONGO_URL

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
        # Very simple fallback for insert
        doc_copy = dict(document)
        if "_id" in doc_copy:
            doc_copy["_id"] = str(doc_copy["_id"])
        
        # Serialize datetime
        for k, v in doc_copy.items():
            if isinstance(v, datetime):
                doc_copy[k] = v.isoformat()

        self.conn.execute(f"INSERT INTO {self.table_name} (data) VALUES (?)", (json.dumps(doc_copy),))
        self.conn.commit()
        class Result:
            inserted_id = 1
        return Result()

    def find_one(self, query):
        # We only support basic find_one for heartbeat and deduplication
        cursor = self.conn.execute(f"SELECT data FROM {self.table_name}")
        rows = cursor.fetchall()
        
        # In-memory filter for SQLite fallback
        for row in rows:
            data = json.loads(row[0])
            match = True
            for k, v in query.items():
                if k not in data:
                    match = False
                    break
                # Special handling for operators like $gte
                if isinstance(v, dict):
                    if "$gte" in v:
                        # String comparison for ISO dates
                        if data[k] < (v["$gte"].isoformat() if isinstance(v["$gte"], datetime) else v["$gte"]):
                            match = False
                            break
                elif data[k] != v:
                    match = False
                    break
            
            if match:
                return data
        return None

    def find_one_and_update(self, query, update, sort=None, return_document=None):
        # Extremely basic fallback atomic update for SQLite
        cursor = self.conn.execute(f"SELECT id, data FROM {self.table_name}")
        rows = cursor.fetchall()
        
        for row in rows:
            row_id = row[0]
            data = json.loads(row[1])
            
            # Check match
            match = True
            for k, v in query.items():
                if k not in data or data[k] != v:
                    match = False
                    break
            
            if match:
                # Apply update
                set_data = update.get("$set", {})
                for k, v in set_data.items():
                    data[k] = v.isoformat() if isinstance(v, datetime) else v
                
                self.conn.execute(f"UPDATE {self.table_name} SET data = ? WHERE id = ?", (json.dumps(data), row_id))
                self.conn.commit()
                return data
                
        return None

    def update_one(self, query, update):
        self.find_one_and_update(query, update)

    def count_documents(self, query):
        return 0  # Fallback stub
        
    def create_index(self, keys, **kwargs):
        pass

class SQLiteFallbackDB:
    def __init__(self):
        self.conn = sqlite3.connect('local_fallback.db', check_same_thread=False)
        self.articles = SQLiteFallbackCollection(self.conn, 'articles')
        self.telemetry = SQLiteFallbackCollection(self.conn, 'telemetry')

_db_instance = None

def get_db():
    global _db_instance
    if _db_instance is not None:
        return _db_instance

    if not MONGO_URL:
        print("WARNING: MONGO_URL is not set. Using SQLite Fallback Database.")
        _db_instance = SQLiteFallbackDB()
        return _db_instance
    
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        _db_instance = client.news_engine
        return _db_instance
    except (ConnectionFailure, ConfigurationError) as e:
        print(f"WARNING: MongoDB connection failed: {e}. Using SQLite Fallback Database.")
        _db_instance = SQLiteFallbackDB()
        return _db_instance

def init_db():
    try:
        db = get_db()
        if isinstance(db, SQLiteFallbackDB):
            print("SQLite fallback initialized.")
            return

        db.articles.create_index("content_hash", unique=True)
        db.articles.create_index("status")
        db.articles.create_index([("priority_score", -1), ("created_at", -1)])
        print("MongoDB initialized and indexes created.")
    except Exception as e:
        print(f"Failed to initialize database indexes: {e}")
