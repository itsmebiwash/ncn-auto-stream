import sys
from config.settings import parse_env
from database.db_client import init_db
from database.db_client import get_db
from ai.groq_manager import process_text_with_groq, verify_image_with_groq_vision
from utils.renderer import render_html_card
from utils.reel_generator import generate_news_reel
import os

def run_dry_run_test():
    print("=== STARTING END-TO-END SYSTEM TEST ===")
    
    # 1. Check Configuration & Keys
    cfg = parse_env()
    print(f"[OK] Configuration loaded. Found {len(cfg.get('GROQ_KEYS', []))} Groq keys.")
    
    # 2. Test DB Initialization
    db = init_db()
    print("[OK] Database connection established.")
    
    # 3. Test Text AI Engine (Groq Text)
    sample_nepali_text = "सवारी चालक अनुमतिपत्र (लाइसेन्स) को विवरणमा त्रुटि भएमा सच्याउने तरिका।"
    ai_result = process_text_with_groq(sample_nepali_text, "")
    if not ai_result:
        print("[FAIL] Groq Text processing failed.")
        return
        
    print(f"[OK] Groq Text Response: Headline = '{ai_result.get('card_headline_english')}'")
    
    # 4. Test Card Renderer
    # We need a sample image. We can use assets/logo.png as a placeholder background
    bg_image = "./assets/logo.png"
    if not os.path.exists(bg_image):
        print(f"[WARN] No sample background found at {bg_image}. Please ensure a valid image exists.")
        
    card_path = "./output/ready/test_card.jpg"
    os.makedirs(os.path.dirname(card_path), exist_ok=True)
    
    success, result_path = render_html_card(
        image_path=bg_image,
        category="NEPAL CENTRAL NEWS",
        headline=ai_result.get('card_headline_english', 'Headline'),
        subtitle=ai_result.get('card_subtitle_english', 'Subtitle'),
        output_path=card_path
    )
    
    if success:
        print(f"[OK] Image Card generated at: {result_path}")
    else:
        print(f"[FAIL] Card Renderer failed: {result_path}")
        return
    
    # 5. Test Reel Generator
    reel_path = generate_news_reel(
        image_card_path=result_path,
        headline=ai_result.get('card_headline_nepali', 'Headline'),
        output_path="./output/ready_reels/test_reel.mp4"
    )
    if reel_path:
        print(f"[OK] Video Reel generated at: {reel_path}")
    else:
        print("[FAIL] Video Reel Generator failed.")
        return
    
    print("=== ALL PIPELINE MODULES PASSED SANITY CHECKS ===")

if __name__ == "__main__":
    run_dry_run_test()
