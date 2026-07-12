import os
import time
import requests
from config.settings import FB_PAGE_ID, FB_ACCESS_TOKEN

def post_reel_to_facebook(article_dict, video_path):
    """
    Implements Meta's 3-step Reels Video API uploading.
    """
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        return False, "Facebook credentials not configured."
        
    if not os.path.exists(video_path):
        return False, "Video file not found."
        
    file_size = os.path.getsize(video_path)
    
    hashtags_list = article_dict.get('hashtags', [])
    hashtags_str = " ".join(hashtags_list) if isinstance(hashtags_list, list) else str(hashtags_list)
    caption_text = article_dict.get('english_description', '')
    source_attr = f"\nSource: {article_dict.get('source_name', 'Nepali News')}"
    
    description = f"{caption_text}\n\n{hashtags_str}{source_attr}"
    
    try:
        # Step 1: Initialize Upload Session
        init_url = f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/video_reels"
        init_payload = {
            'upload_phase': 'start',
            'access_token': FB_ACCESS_TOKEN
        }
        
        init_resp = requests.post(init_url, data=init_payload, timeout=20)
        init_resp.raise_for_status()
        init_data = init_resp.json()
        
        video_id = init_data.get('video_id')
        upload_url = init_data.get('upload_url')
        
        if not video_id or not upload_url:
            return False, "Failed to initialize upload session."
            
        # Step 2: Transfer Video Binary
        headers = {
            'Authorization': f'OAuth {FB_ACCESS_TOKEN}',
            'file_offset': '0'
        }
        
        with open(video_path, 'rb') as f:
            upload_resp = requests.post(upload_url, headers=headers, data=f, timeout=60)
            upload_resp.raise_for_status()
            
        # Step 3: Finish & Publish Reel
        finish_payload = {
            'upload_phase': 'finish',
            'video_id': video_id,
            'video_state': 'PUBLISHED',
            'description': description,
            'access_token': FB_ACCESS_TOKEN
        }
        
        finish_resp = requests.post(init_url, data=finish_payload, timeout=20)
        finish_resp.raise_for_status()
        finish_data = finish_resp.json()
        
        if finish_data.get('success'):
            return True, video_id
        else:
            return False, "Finish phase did not return success."
            
    except requests.exceptions.HTTPError as e:
        error_msg = str(e)
        if e.response is not None:
            try:
                error_msg = str(e.response.json())
            except:
                error_msg = e.response.text
        return False, f"Reel API Error: {error_msg}"
    except Exception as e:
        return False, f"Reel Upload Exception: {str(e)}"
