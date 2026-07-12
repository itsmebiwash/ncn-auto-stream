import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KeyPool:
    def __init__(self, name, keys):
        if not keys:
            logger.warning(f"No keys provided for pool {name}.")
        self.name = name
        self.keys = [{"key": k, "blocked_until": 0} for k in keys]
        self.current_index = 0

    def get_active_key(self):
        """Returns the first active key. Rotates if necessary. Returns None if all blocked."""
        if not self.keys:
            return None
            
        start_index = self.current_index
        while True:
            key_info = self.keys[self.current_index]
            if time.time() >= key_info["blocked_until"]:
                return key_info["key"]
                
            # Move to next key
            self.current_index = (self.current_index + 1) % len(self.keys)
            
            # If we looped all the way around, all keys are blocked
            if self.current_index == start_index:
                logger.error(f"[{self.name}] All keys are currently blocked due to rate limits.")
                return None

    def mark_key_blocked(self, key_str, retry_after_seconds=30):
        """Blocks a specific key for `retry_after_seconds` due to HTTP 429."""
        for k in self.keys:
            if k["key"] == key_str:
                k["blocked_until"] = time.time() + retry_after_seconds
                logger.warning(f"[{self.name}] Key {key_str[:5]}... blocked for {retry_after_seconds}s.")
                # Move index to next to failover immediately
                self.current_index = (self.current_index + 1) % len(self.keys)
                break

from .settings import GROQ_API_KEYS

groq_pool = KeyPool("Groq", GROQ_API_KEYS)
