import sys
from database.db_client import init_db
from job_queue.worker import start_worker

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

if __name__ == "__main__":
    print("Initializing Database...")
    init_db()
    
    print("Starting Priority Queue Worker...")
    start_worker()
