import time
import requests
from config.settings import FB_PAGE_ID, FB_ACCESS_TOKEN

def fetch_post_insights(fb_post_id: str) -> dict:
    """
    Fetches post impressions and engagement metrics from Meta Graph API.
    Returns a dict with impressions and specific engagement types.
    """
    if not FB_ACCESS_TOKEN:
        print("[Insights] FB_ACCESS_TOKEN is not set.")
        return {}

    url = f"https://graph.facebook.com/v19.0/{fb_post_id}/insights"
    params = {
        'metric': 'post_impressions_unique,post_engagements_by_type',
        'access_token': FB_ACCESS_TOKEN
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        metrics = {
            'impressions': 0,
            'clicks': 0,
            'shares': 0,
            'likes': 0
        }
        
        for item in data.get('data', []):
            name = item.get('name')
            if name == 'post_impressions_unique':
                if item.get('values'):
                    metrics['impressions'] = item['values'][0].get('value', 0)
            elif name == 'post_engagements_by_type':
                if item.get('values'):
                    val_dict = item['values'][0].get('value', {})
                    metrics['clicks'] = val_dict.get('link_clicks', 0) + val_dict.get('other_clicks', 0)
                    metrics['shares'] = val_dict.get('share', 0)
                    metrics['likes'] = val_dict.get('like', 0)
                    
        return metrics
    except Exception as e:
        print(f"[Insights Error for {fb_post_id}] {e}")
        return {}
