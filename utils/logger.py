import os
from datetime import datetime, timezone

LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
FEEDBACK_FILE = os.path.join(LOGS_DIR, 'feedback.txt')

def log_feedback(article, fb_post_id=None, reel_id=None, processing_time_sec=0, error_msg=None, ai_suggestions=None):
    """
    Appends diagnostic logs and errors to ./logs/feedback.txt.
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    article_id = str(article.get('_id', 'unknown'))
    headline = article.get('english_headline', 'No Headline')
    template_used = article.get('template_used', 'unknown')
    
    status = "SUCCESS" if fb_post_id else "FAILED"
    
    # Image context status
    image_url = article.get('original_image_url')
    image_status = "Used Pexels Fallback" if "pexels.com" in str(image_url) else "Used Scraped Image"
    
    with open(FEEDBACK_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] ARTICLE ID: {article_id}\n")
        f.write(f"  Status: {status}\n")
        f.write(f"  Headline: {headline}\n")
        f.write(f"  Template Used: {template_used}\n")
        f.write(f"  Image Context: {image_status} (URL: {image_url})\n")
        f.write(f"  Processing Time: {processing_time_sec:.1f}s\n")
        
        if fb_post_id:
            f.write(f"  Facebook Post ID: {fb_post_id}\n")
        if reel_id:
            f.write(f"  Reel Post ID: {reel_id}\n")
            
        if error_msg:
            f.write(f"  ERROR: {error_msg}\n")
            
        if ai_suggestions:
            f.write(f"  AI Suggestion: {ai_suggestions}\n")
            
        f.write("-" * 65 + "\n")
