import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEYS = [k.strip() for k in os.getenv("GROQ_API_KEYS", os.getenv("GROQ_KEYS", "")).split(",") if k.strip()]

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN", "")

MONGO_URL = os.getenv("MONGO_URL", "")

WORKER_INTERVAL_SECONDS = int(os.getenv("WORKER_INTERVAL_SECONDS", "240"))
SCRAPER_INTERVAL_HOURS = int(os.getenv("SCRAPER_INTERVAL_HOURS", "1"))
