import json
import time
import requests
import google.generativeai as genai
from config.key_manager import gemini_pool

def verify_image_with_gemini(image_url):
    """
    Analyzes an image using Gemini to verify if it's an editorial photo.
    Returns: {"is_faulty_image": boolean, "reason": "string"}
    """
    max_attempts = 3
    prompt = 'Analyze this image. Is it an editorial photo belonging to a news story, or is it a website logo, promotional banner, stock advertisement, or broken graphic? Output strictly in JSON format: {"is_faulty_image": boolean, "reason": "string"}.'

    try:
        # Download image bytes first
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        image_bytes = resp.content
    except Exception as e:
        return {"is_faulty_image": True, "reason": f"Failed to download image: {str(e)}"}

    for attempt in range(max_attempts):
        api_key = gemini_pool.get_active_key()
        if not api_key:
            return {"is_faulty_image": True, "reason": "All Gemini keys blocked"}

        genai.configure(api_key=api_key)
        
        try:
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            
            # Gemini requires specific image format dictionary
            image_parts = [
                {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            ]
            
            response = model.generate_content(
                [prompt, image_parts[0]],
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            
            return json.loads(response.text)
            
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str:
                gemini_pool.mark_key_blocked(api_key, retry_after_seconds=60)
            else:
                print(f"[Gemini Error] {e}")
                
            time.sleep(1)

    return {"is_faulty_image": True, "reason": "Max retries exceeded or parsing failed"}
