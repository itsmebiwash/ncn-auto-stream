import json
import time
from groq import Groq
from config.key_manager import groq_pool


def extract_retry_after(error_str):
    if "retry-after" in error_str.lower():
        return 30
    return 30


def process_text_with_groq(title, content="", category="General"):
    """
    Analyzes a news title+body using Groq llama-3.1-8b-instant.
    Returns parsed JSON or None on failure.
    category = source-level hint (General, Business, etc.) — may be overridden
    by the AI-detected article_category in the response.
    """
    system_prompt = '''You are an objective, facts-only news editor and social media viral strategist.
Analyze the provided Nepali news article.

Strict Formatting Requirements:
1. Identify if this is a real news story or an advertisement, sponsored post, or non-news notice.

2. `article_category`: Classify the article into EXACTLY ONE of these categories based on its CONTENT
   (ignore the source website — a politics article from a business site is still Politics):
   Politics | Crime | Business | Sports | Health | Technology | Education |
   Entertainment | International | Environment | Science | Lifestyle | Weather | Opinion | General

3. Language rule:
   - If article_category is "International": write card_headline_nepali, card_subtitle_nepali,
     and fb_caption_text ENTIRELY in English.
   - For all other categories: write ALL three ENTIRELY in Nepali (Devanagari script).

4. `card_headline_nepali`: 4 to 7 words MAX. Short, punchy, realistic news headline.

5. `card_subtitle_nepali`: 12 to 20 words. Add context without revealing all details.

6. `fb_caption_text`: Strictly factual report covering Who, What, When, Where, Why, How.
   CRITICAL RULES for fb_caption_text:
   - Write EACH sentence ONCE. NEVER repeat the same idea in different words.
   - Maximum 4 sentences total.
   - Do NOT include ANY source link, URL, or placeholder like "[स्रोतको नाम]" or "[Source]".
   - The source is appended automatically — do not write it yourself.

7. `priority_score`: Float 1.0 to 10.0:
   - Scope & Impact 40% (policy, national security, public safety, deaths)
   - Urgency 30% (breaking news, within last 2 hours)
   - Virality 30% (accidents, protests, sports wins, major crime)

8. `hashtags`: ONLY English/ASCII. NEVER Devanagari. Always include #NepalCentralNews and #NCN.
   CORRECT: ["#NepalNews", "#Kathmandu", "#NepalCentralNews", "#NCN"]
   WRONG:   ["#नेपाल", "#काठमाडौं"]  ← DISCARDED automatically.

9. `pexels_search_keywords`: 2-3 SPECIFIC visual phrases. NOT "news", "paper", "typewriter".

Respond ONLY with this exact JSON:
{
  "is_advertisement_or_promo": false,
  "article_category": "Politics",
  "priority_score": 7.5,
  "card_headline_nepali": "string (4-7 words)",
  "card_subtitle_nepali": "string (12-20 words)",
  "fb_caption_text": "string (max 4 sentences, no repeats, no source placeholder)",
  "hashtags": ["#NepalCentralNews", "#Nepal", "#BreakingNews", "#Kathmandu", "#NCN"],
  "pexels_search_keywords": ["keyword 1", "keyword 2"]
}'''

    user_prompt = f"Source category hint: {category}\nTitle: {title}\nBody: {content}"


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
            data = json.loads(response_content)

            # Ensure priority_score exists (fall back to virality_score for old schema)
            if "priority_score" not in data:
                data["priority_score"] = data.get("virality_score", 5.0)

            return data

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
    DEPRECATED: llama-3.2-90b-vision-preview was decommissioned by Groq.
    The scraper now uses a lightweight HTTP HEAD check instead (_is_image_accessible).
    This function is kept for backward compatibility but always returns 'not faulty'.
    """
    return {"is_faulty_or_ad_image": False, "reason": "vision_check_replaced_by_http_head"}

