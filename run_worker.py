from db.database import init_db
from queue.worker import start_worker

if __name__ == "__main__":
    print("Initializing Database...")
    init_db()
    
    print("Starting Priority Queue Worker...")
    start_worker()
