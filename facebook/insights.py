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

    url = f"https://graph.facebook.com/v21.0/{fb_post_id}/insights"
    params = {
        'metric': 'post_impressions_unique,post_clicks,post_reactions_by_type_total',
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
            elif name == 'post_clicks':
                if item.get('values'):
                    metrics['clicks'] = item['values'][0].get('value', 0)
            elif name == 'post_reactions_by_type_total':
                if item.get('values'):
                    val_dict = item['values'][0].get('value', {})
                    metrics['likes'] = sum(val_dict.values()) if val_dict else 0
                    
        return metrics
    except Exception as e:
        print(f"[Insights Error for {fb_post_id}] {e}")
        return {}


def fetch_page_insights() -> dict:
    """
    Fetches overall page impressions and engagement metrics from Meta Graph API.
    Returns a dict with page_impressions_unique and page_engaged_users.
    """
    if not FB_ACCESS_TOKEN or not FB_PAGE_ID:
        print("[Insights] FB_ACCESS_TOKEN or FB_PAGE_ID is not set.")
        return None

    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/insights"
    # Using period day to get daily insights
    params = {
        'metric': 'page_impressions_unique,page_engaged_users',
        'period': 'day',
        'access_token': FB_ACCESS_TOKEN
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        metrics = {
            'page_impressions_unique': 0,
            'page_engaged_users': 0
        }
        
        for item in data.get('data', []):
            name = item.get('name')
            # Insights often return an array of values for dates. We take the last available value (most recent).
            if name == 'page_impressions_unique':
                if item.get('values'):
                    metrics['page_impressions_unique'] = item['values'][-1].get('value', 0)
            elif name == 'page_engaged_users':
                if item.get('values'):
                    metrics['page_engaged_users'] = item['values'][-1].get('value', 0)
                    
        return metrics
    except Exception as e:
        print(f"[Insights Error for Page {FB_PAGE_ID}] {e}")
        return None
