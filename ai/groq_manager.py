import json
import time
from groq import Groq
from config.key_manager import groq_pool

def extract_retry_after(error_str):
    if "retry-after" in error_str.lower():
        return 30
    return 30

def process_text_with_groq(title, content=""):
    """
    Analyzes the title/body using Groq llama-3.1-8b-instant.
    """
    system_prompt = '''You are a senior news editor and social media viral growth strategist. 
Analyze the following Nepali news article. 

Your tasks:
1. Identify if this is a real news story or an advertisement, sponsored post, self-promotion, or non-news notice.
2. Evaluate virality potential and timeliness (1 to 10 scale).
3. If the news is LOCAL to Nepal, write the headline, subtitle, and caption ENTIRELY in Nepali language.
4. If the news is INTERNATIONAL, write the headline, subtitle, and caption ENTIRELY in English language.
5. Extract SPECIFIC contextual search keywords for image fetching (DO NOT use generic terms like "news", "typewriter", "paper", or "press").

Respond ONLY with this JSON structure:
{
  "is_advertisement_or_promo": boolean,
  "is_duplicate_story": boolean,
  "virality_score": number,
  "card_headline_nepali": "string (5-8 words max, short & punchy for news card)",
  "card_subtitle_nepali": "string (10-12 words highlight summary)",
  "fb_caption_text": "string (SEO-optimized post body with key facts, engaging tone, and source credit)",
  "hashtags": ["#NepalCentralNews", "#Nepal", "#CategoryHashtag"],
  "pexels_search_keywords": ["specific context 1", "specific context 2"] 
}'''
    
    user_prompt = f"Title: {title}\nBody: {content}"

    max_attempts = 5
    for attempt in range(max_attempts):
        api_key = groq_pool.get_active_key()
        if not api_key:
            print("[Groq Text] All keys blocked.")
            return None

        client = Groq(api_key=api_key)
        
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model="llama-3.1-8b-instant",
                response_format={"type": "json_object"},
                temperature=0.2
            )
            
            response_content = chat_completion.choices[0].message.content
            return json.loads(response_content)
            
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate limit" in error_str:
                retry_after = extract_retry_after(error_str)
                groq_pool.mark_key_blocked(api_key, retry_after_seconds=retry_after)
            else:
                print(f"[Groq Text Error] {e}")
                
            time.sleep(1)

    return None


def verify_image_with_groq_vision(image_url):
    """
    Verifies image using Groq llama-3.2-11b-vision-preview.
    """
    system_prompt = '''Analyze this news website image.
Determine if this image is a genuine editorial photo of a news event/person/location, OR if it is a website logo, stock promotional banner, advertisement, or broken graphic.

Respond ONLY with this JSON structure:
{
  "is_faulty_or_ad_image": boolean,
  "reason": "string"
}'''

    max_attempts = 5
    for attempt in range(max_attempts):
        api_key = groq_pool.get_active_key()
        if not api_key:
            print("[Groq Vision] All keys blocked.")
            return {"is_faulty_or_ad_image": True, "reason": "All keys blocked"}

        client = Groq(api_key=api_key)
        
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": system_prompt},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                model="llama-3.2-90b-vision-preview",
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            response_content = chat_completion.choices[0].message.content
            return json.loads(response_content)
            
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate limit" in error_str:
                retry_after = extract_retry_after(error_str)
                groq_pool.mark_key_blocked(api_key, retry_after_seconds=retry_after)
            else:
                print(f"[Groq Vision Error] {e}")
                return {"is_faulty_or_ad_image": True, "reason": str(e)}
                
            time.sleep(1)

    return {"is_faulty_or_ad_image": True, "reason": "Max retries exceeded"}
