import os
import json
from groq import Groq

def extractMetadata(headline: str, newsBody: str) -> dict:
    """
    Uses Groq API with llama-3.3-70b-versatile to extract category, keywords, and sentiment.
    Returns a dictionary:
    {
        "category": "Politics" | "Crime" | "Entertainment" | "Sports" | "General",
        "keywords": ["keyword1", "keyword2", ...],
        "sentiment": "Positive" | "Neutral" | "Negative"
    }
    """
    keys = os.getenv("GROQ_API_KEYS", os.getenv("GROQ_KEYS", ""))
    api_key = keys.split(",")[0].strip() if keys else os.getenv("GROQ_API_KEY", "")
    client = Groq(api_key=api_key)

    prompt = f"""
    Analyze the following news headline and body. Extract the category, key entities/keywords (up to 5), and the sentiment.
    Headline: {headline}
    Body: {newsBody}

    Output valid JSON ONLY. Do not include markdown formatting or extra text.
    Format exactly as:
    {{
        "category": "Politics" | "Crime" | "Entertainment" | "Sports" | "General",
        "keywords": ["keyword1", "keyword2"],
        "sentiment": "Positive" | "Neutral" | "Negative"
    }}
    """
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        
        content = completion.choices[0].message.content.strip()
        # Clean up any potential markdown formatting from the response
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
            
        data = json.loads(content.strip())
        
        # Validate data
        category = data.get("category", "General")
        if category not in ["Politics", "Crime", "Entertainment", "Sports", "General"]:
            category = "General"
            
        sentiment = data.get("sentiment", "Neutral")
        if sentiment not in ["Positive", "Neutral", "Negative"]:
            sentiment = "Neutral"
            
        keywords = data.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
            
        return {
            "category": category,
            "keywords": keywords[:5],
            "sentiment": sentiment
        }
    except Exception as e:
        print(f"Error extracting metadata via Groq: {e}")
        return {
            "category": "General",
            "keywords": [],
            "sentiment": "Neutral"
        }
