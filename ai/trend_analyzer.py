import json
import datetime
from groq import Groq
from database.db_client import get_db
from facebook.insights import fetch_post_insights
from config.key_manager import groq_pool

class TrendAnalyzer:
    def __init__(self):
        self.db = get_db()
        api_key = groq_pool.get_active_key()
        self.groq_client = Groq(api_key=api_key) if api_key else None
        self.CACHE_HOURS = 24

    def _get_cached_trends(self):
        try:
            record = self.db.telemetry.find_one(
                {'type': 'trending_topics'},
                sort=[('updated_at', -1)]
            )
            if record and 'updated_at' in record:
                # Ensure updated_at is offset-aware UTC for comparison
                updated_at = record['updated_at']
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=datetime.timezone.utc)
                    
                age = datetime.datetime.now(datetime.timezone.utc) - updated_at
                if age.total_seconds() < self.CACHE_HOURS * 3600:
                    return record.get('trends', [])
        except Exception as e:
            print(f"[Trend Analyzer] Cache read error: {e}")
        return None

    def _save_trends(self, trends):
        try:
            self.db.telemetry.update_one(
                {'type': 'trending_topics'},
                {'$set': {
                    'trends': trends,
                    'updated_at': datetime.datetime.now(datetime.timezone.utc)
                }},
                upsert=True
            )
        except Exception as e:
            print(f"[Trend Analyzer] Cache write error: {e}")

    def analyze_current_trends(self):
        """
        Analyzes the last 15 posts, fetches their engagement, and uses Groq to determine
        the overarching trending topics. Returns a list of keywords/categories.
        """
        cached = self._get_cached_trends()
        if cached is not None:
            print(f"[Trend Analyzer] Using cached trends: {cached}")
            return cached

        print("[Trend Analyzer] No recent cache. Analyzing latest posts for engagement trends...")
        if not self.groq_client:
            print("[Trend Analyzer] No Groq API key available. Skipping trend analysis.")
            return []
        try:
            # Fetch last 15 posted articles
            recent_posts = list(self.db.articles.find(
                {'status': 'posted', 'facebook_post_id': {'$exists': True, '$ne': None}},
                sort=[('posted_at', -1)],
                limit=15
            ))

            if not recent_posts:
                print("[Trend Analyzer] Not enough posted history to analyze trends.")
                return []

            post_data = []
            for post in recent_posts:
                fb_id = post.get('facebook_post_id')
                insights = fetch_post_insights(fb_id)
                
                # Calculate an engagement score (impressions + clicks * 2 + shares * 5)
                score = insights.get('impressions', 0) + (insights.get('clicks', 0) * 2) + (insights.get('shares', 0) * 5)
                
                post_data.append({
                    'title': post.get('english_headline', post.get('original_title', '')),
                    'category': post.get('category', 'general'),
                    'score': score
                })
                
            # Sort by score descending and take the top 5
            post_data.sort(key=lambda x: x['score'], reverse=True)
            top_posts = post_data[:5]
            
            if not top_posts or sum(p['score'] for p in top_posts) == 0:
                print("[Trend Analyzer] No significant engagement found on recent posts.")
                self._save_trends([])
                return []
                
            # Prepare prompt for Groq
            prompt_content = "Analyze these highly engaging recent news posts and extract 2-4 broad trending topics or categories. Return ONLY a JSON array of strings (e.g. [\"Politics\", \"Weather\", \"Local Crime\"]). Do not include any other text.\n\nPosts:\n"
            for p in top_posts:
                prompt_content += f"- Title: {p['title']} (Category: {p['category']})\n"
                
            response = self.groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": "You are a helpful data analyst. Output only a JSON array of strings."},
                    {"role": "user", "content": prompt_content}
                ],
                temperature=0.3,
                max_tokens=100
            )
            
            output_text = response.choices[0].message.content.strip()
            
            # Clean up potential markdown formatting in JSON response
            if output_text.startswith('```json'):
                output_text = output_text[7:]
            if output_text.startswith('```'):
                output_text = output_text[3:]
            if output_text.endswith('```'):
                output_text = output_text[:-3]
                
            trends = json.loads(output_text.strip())
            
            if isinstance(trends, list):
                print(f"[Trend Analyzer] Identified new trends: {trends}")
                self._save_trends(trends)
                return trends
            else:
                return []
                
        except Exception as e:
            print(f"[Trend Analyzer Error] {e}")
            return []
