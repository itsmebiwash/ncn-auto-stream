import os
import time
import requests
from config.settings import FB_PAGE_ID, FB_ACCESS_TOKEN
from facebook.publisher import build_facebook_caption


def post_reel_to_facebook(article_dict, video_path):
    """
    Implements Meta's 3-step Reels Video API upload protocol.
    Returns (True, video_id) or (False, error_msg).
    """
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        return False, "Facebook credentials not configured."

    if not os.path.exists(video_path):
        return False, f"Video file not found: {video_path}"

    description = build_facebook_caption(
        fb_caption_text=article_dict.get("english_description", ""),
        hashtags_list=article_dict.get("hashtags", []),
        source_name=article_dict.get("source_name", "Nepal Central News"),
        category=article_dict.get("category", "")
    )

    try:
        # ── Step 1: Initialise upload session ────────────────────
        init_url = f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/video_reels"
        init_resp = requests.post(
            init_url,
            data={"upload_phase": "start", "access_token": FB_ACCESS_TOKEN},
            timeout=20
        )
        init_resp.raise_for_status()
        init_data = init_resp.json()

        video_id  = init_data.get("video_id")
        upload_url = init_data.get("upload_url")

        if not video_id or not upload_url:
            return False, f"Failed to initialise upload session: {init_data}"

        # ── Step 2: Transfer video binary ────────────────────────
        # rupload.facebook.com requires: offset, Content-Length, X-Entity-Length
        file_size = os.path.getsize(video_path)
        with open(video_path, "rb") as f:
            upload_resp = requests.post(
                upload_url,
                headers={
                    "Authorization": f"OAuth {FB_ACCESS_TOKEN}",
                    "offset": "0",
                    "Content-Length": str(file_size),
                    "X-Entity-Length": str(file_size),
                },
                data=f,
                timeout=300
            )
            if upload_resp.status_code not in (200, 204):
                return False, f"Reel upload Step 2 error: {upload_resp.text}"

        # ── Step 3: Finish & publish ─────────────────────────────
        finish_resp = requests.post(
            init_url,
            data={
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description,
                "access_token": FB_ACCESS_TOKEN
            },
            timeout=20
        )
        finish_resp.raise_for_status()
        finish_data = finish_resp.json()

        if finish_data.get("success"):
            return True, video_id

        return False, f"Finish phase did not return success: {finish_data}"

    except requests.exceptions.HTTPError as e:
        error_msg = str(e)
        if e.response is not None:
            try:
                error_msg = str(e.response.json())
            except Exception:
                error_msg = e.response.text
        return False, f"Reel API HTTPError: {error_msg}"

    except Exception as e:
        return False, f"Reel Upload Exception: {e}"
