import json
import time
from groq import Groq
from config.key_manager import groq_pool

def process_text_with_groq(original_title, original_url):
    """
    Analyzes the title/URL using Groq llama-3.1-8b-instant.
    Returns a dictionary matching the required JSON output schema.
    Returns None if all keys are blocked or max retries exceeded.
    """
    system_prompt = '''
You are an expert news aggregator and English editor. 
Your task is to analyze the given Nepali news title and URL, translate it to high-quality, professional English, and strip away any promotional spam (e.g., "Download Nagarik Network APP", "Credit", "Advertisement").
Output strictly in JSON format.

JSON Schema:
{
  "is_duplicate_or_redundant": boolean, // true if it looks like an old duplicated story
  "is_advertisement_or_promotional": boolean, // true if it contains promos, app downloads, or sponsored content
  "relevancy_score": number, // 1 to 10 based on timeliness and impact
  "virality_potential_score": number, // 1 to 10 based on broad audience interest
  "english_headline": "string", // Clean, professional English translation. NO spam.
  "english_caption": "string", // Clean, professional English summary caption. NO spam.
  "english_description": "string", // Detailed English description.
  "pexels_search_keywords": ["string", "string"],
  "topic_slug": "string" // A 3 to 4 word, lowercase, hyphenated slug summarizing the topic (e.g. "nepal-politics-update")
}
'''
    user_prompt = f"Title: {original_title}\nURL: {original_url}"

    max_attempts = 3
    for attempt in range(max_attempts):
        api_key = groq_pool.get_active_key()
        if not api_key:
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
                groq_pool.mark_key_blocked(api_key, retry_after_seconds=30)
            else:
                print(f"[Groq Error] {e}")
                
            time.sleep(1)

    return None
