import time
import datetime
from database.db_client import get_db
from facebook.insights import fetch_page_insights

class TrustEngine:
    """
    Dynamic Facebook Publishing & Trust Engine
    Monitors organic reach to adjust posting volume to avoid shadowbans.
    """
    def __init__(self):
        self.db = get_db()
        self.MIN_POSTS = 2
        self.MAX_POSTS = 15
        
    def _record_telemetry(self, reach):
        """Records the current cycle's reach to the database."""
        try:
            self.db.telemetry.insert_one({
                'type': 'page_reach',
                'reach': reach,
                'created_at': datetime.datetime.now(datetime.timezone.utc)
            })
        except Exception as e:
            print(f"[Trust Engine] Error recording telemetry: {e}")

    def _get_rolling_average(self, days=7):
        """Calculates the 7-day rolling average of page reach."""
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
            records = list(
                self.db.telemetry
                .find({'type': 'page_reach', 'created_at': {'$gte': cutoff}})
                .sort('created_at', -1)
            )

            if not records:
                return None

            total_reach = sum(r.get('reach', 0) for r in records)
            return total_reach / len(records)
        except Exception as e:
            print(f"[Trust Engine] Error calculating rolling average: {e}")
            return None

    def _get_recent_drops(self, average):
        """Checks if the last 3 cycles all had a >= 50% drop compared to average."""
        try:
            records = list(
                self.db.telemetry
                .find({'type': 'page_reach'})
                .sort('created_at', -1)
                .limit(3)
            )

            if len(records) < 3:
                return False

            threshold = average * 0.5
            for r in records:
                if r.get('reach', 0) > threshold:
                    return False
            return True
        except Exception as e:
            print(f"[Trust Engine] Error checking recent drops: {e}")
            return False

    def evaluate_page_health(self):
        """
        Determines the current state: SHADOWBANNED, RECOVERING, or HEALTHY.
        Returns a tuple: (state, posts_per_cycle, skip_links)
        """
        try:
            insights = fetch_page_insights()
            
            # API Error Check
            if insights is None or 'page_impressions_unique' not in insights:
                print("[Trust Engine] Meta API Error or timeout. Defaulting to safe fallback.")
                return ('API_ERROR', 3, False)
                
            current_reach = insights.get('page_impressions_unique', 0)
            self._record_telemetry(current_reach)
            
            rolling_avg = self._get_rolling_average(days=7)
            
            if rolling_avg is None or rolling_avg == 0:
                # Not enough data, assume healthy
                return ('HEALTHY', self.MAX_POSTS, False)
                
            is_shadowbanned = self._get_recent_drops(rolling_avg)
            
            if is_shadowbanned:
                print("[Trust Engine] SHADOWBAN DETECTED. Applying strict limits.")
                return ('SHADOWBANNED', self.MIN_POSTS, True)
                
            # If current reach is below 75% of average, we are recovering
            if current_reach < (rolling_avg * 0.75):
                print("[Trust Engine] Page is recovering. Applying moderate limits.")
                recovery_posts = max(self.MIN_POSTS, int(self.MAX_POSTS * 0.5))
                return ('RECOVERING', recovery_posts, True)
                
            print("[Trust Engine] Page is HEALTHY.")
            return ('HEALTHY', self.MAX_POSTS, False)
            
        except Exception as e:
            print(f"[Trust Engine API Error] {e}. Defaulting to safe fallback.")
            return ('API_ERROR', 3, False)
