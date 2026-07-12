import requests
import json
import time
from config.settings import FB_PAGE_ID, FB_ACCESS_TOKEN


def parse_usage_header(header_value):
    """Parses X-Page-Usage or X-App-Usage Meta headers."""
    if not header_value:
        return 0
    try:
        data = json.loads(header_value)
        return max(data.get("call_count", 0), data.get("total_cputime", 0), data.get("total_time", 0))
    except Exception:
        return 0


def build_facebook_caption(fb_caption_text, hashtags_list, source_name, category=""):
    """
    Constructs the full Facebook post caption.
    Format:
        <factual 5W+1H body>

        स्रोत / Source: <source_name>

        #Hashtag1 #Hashtag2 ...
    """
    hashtag_str = " ".join(hashtags_list) if isinstance(hashtags_list, list) else str(hashtags_list)

    if category.lower() == "international":
        source_label = f"Source: {source_name}"
    else:
        source_label = f"स्रोत: {source_name}"

    return f"{fb_caption_text}\n\n{source_label}\n\n{hashtag_str}"


def post_to_facebook(article_dict):
    """
    Posts a rendered 1080x1350 card image to Facebook Feed.
    Returns (True, post_id) or (False, error_msg).
    """
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        return False, "Facebook credentials not configured."

    image_path = article_dict.get("final_image_path")
    if not image_path:
        return False, "No valid image path to post."

    caption = build_facebook_caption(
        fb_caption_text=article_dict.get("english_description", ""),
        hashtags_list=article_dict.get("hashtags", []),
        source_name=article_dict.get("source_name", "Nepal Central News"),
        category=article_dict.get("category", "")
    )

    url = f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/photos"
    payload = {
        "access_token": FB_ACCESS_TOKEN,
        "message": caption,
        "published": "true"
    }

    try:
        with open(image_path, "rb") as f:
            files = {"source": f}
            response = requests.post(url, data=payload, files=files, timeout=30)

        # Check rate limits
        x_page_usage = response.headers.get("X-Page-Usage")
        x_app_usage  = response.headers.get("X-App-Usage")
        usage_percent = max(parse_usage_header(x_page_usage), parse_usage_header(x_app_usage))

        if usage_percent >= 80:
            print(f"[RATE WARNING] Meta quota at {usage_percent}%. Pausing 15 minutes.")
            time.sleep(900)

        if response.status_code == 429:
            print("[RATE ERROR] HTTP 429 from Meta. Pausing 30 minutes.")
            time.sleep(1800)
            return False, "pause: HTTP 429"

        response_data = response.json()

        if "error" in response_data:
            err_code = response_data["error"].get("code")
            if err_code == 368:
                print("[SPAM WARNING] Error 368 from Meta. Pausing 30 minutes.")
                time.sleep(1800)
                return False, "pause: Error 368"
            return False, str(response_data["error"])

        if "id" in response_data:
            return True, response_data["id"]

        return False, "Unknown response format."

    except Exception as e:
        return False, f"Exception during post: {e}"
