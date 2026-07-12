import os
from datetime import datetime, timezone, timedelta
from db.database import get_db

def record_laptop_heartbeat():
    """Records the active laptop status to MongoDB telemetry collection."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return
    try:
        db = get_db()
        db.telemetry.update_one(
            {"device": "laptop"},
            {"$set": {"last_active": datetime.now(timezone.utc)}},
            upsert=True
        )
    except Exception as e:
        print(f"[Heartbeat Error] Failed to write laptop heartbeat: {e}")

def is_laptop_active():
    """Checks if the laptop is currently running based on DB heartbeat."""
    try:
        db = get_db()
        hb = db.telemetry.find_one({"device": "laptop"})
        if hb:
            last_active = hb["last_active"]
            # Convert to offset-aware utc if offset-naive
            if last_active.tzinfo is None:
                last_active = last_active.replace(tzinfo=timezone.utc)
            
            diff_minutes = (datetime.now(timezone.utc) - last_active).total_seconds() / 60.0
            return diff_minutes < 25.0
    except Exception as e:
        print(f"[Heartbeat Check Error] {e}")
    return False
