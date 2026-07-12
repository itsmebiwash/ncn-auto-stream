import json
import time
import requests
from config.settings import FB_PAGE_ID, FB_ACCESS_TOKEN

def parse_usage_header(header_value):
    """Parses X-Page-Usage or X-App-Usage headers like: {'call_count': 10, 'total_cputime': 12}"""
    if not header_value:
        return 0
    try:
        data = json.loads(header_value)
        return max(data.get("call_count", 0), data.get("total_cputime", 0), data.get("total_time", 0))
    except:
        return 0

def post_to_facebook(article_dict):
    """
    Posts an image and text to Facebook Graph API.
    Returns (True, post_id) or (False, error_msg).
    Handles rate limits and usage ceilings.
    """
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        return False, "Facebook credentials not configured."
        
    url = f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/photos"
    
    hashtags_list = article_dict.get('hashtags', [])
    hashtags_str = " ".join(hashtags_list) if isinstance(hashtags_list, list) else str(hashtags_list)
    
    caption_text = article_dict.get('english_description', '')
    source_attr = f"\nSource: {article_dict.get('source_name', 'Nepali News')}"
    
    caption = f"{caption_text}\n\n{hashtags_str}{source_attr}"
    payload = {
        'access_token': FB_ACCESS_TOKEN,
        'message': caption,
        'published': 'true'
    }
    
    image_path = article_dict.get('final_image_path')
    if not image_path:
        return False, "No valid image path to post."
        
    try:
        with open(image_path, 'rb') as f:
            files = {'source': f}
            response = requests.post(url, data=payload, files=files, timeout=30)
            
        # Check rate limits in headers BEFORE evaluating status
        x_page_usage = response.headers.get("X-Page-Usage")
        x_app_usage = response.headers.get("X-App-Usage")
        
        usage_percent = max(parse_usage_header(x_page_usage), parse_usage_header(x_app_usage))
        
        if usage_percent >= 80:
            print(f"[RATE WARNING] Meta quota at {usage_percent}%. Pausing queue worker for 15 minutes.")
            time.sleep(900)
            
        if response.status_code == 429:
            print("[RATE ERROR] HTTP 429 received from Meta. Pausing queue worker for 30 minutes.")
            time.sleep(1800)
            return False, "pause: HTTP 429"
            
        response_data = response.json()
        
        if 'error' in response_data:
            err_code = response_data['error'].get('code')
            if err_code == 368:
                print("[SPAM WARNING] Meta returned error 368. Pausing for 30 minutes.")
                time.sleep(1800)
                return False, "pause: Error 368"
            return False, str(response_data['error'])
            
        if 'id' in response_data:
            return True, response_data['id']
            
        return False, "Unknown response format."

    except Exception as e:
        return False, f"Exception during post: {str(e)}"
