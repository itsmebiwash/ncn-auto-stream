import os
import sys

# Hack to import from main
sys.path.append(os.path.abspath('.'))
from html2image import Html2Image
from main import generate_news_card

def make_hti():
    h = Html2Image(size=(1080, 1350))
    return h

OUTPUT_DIR = "C:/Users/biwas/.gemini/antigravity-ide/brain/3f880b6b-66bd-43c5-9c31-9cacc2a714f4/scratch"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

hti = make_hti()
hti.output_path = OUTPUT_DIR

samples = [
    ("POLITICS", "Prime Minister Announces New Economic Policy in Parliament", "LATEST", "UPDATE"),
    ("BUSINESS", "Stock Market Surges to Record High Following Tax Cuts", "MARKET", "BULL RUN"),
    ("TECH", "New AI Model Released With Human-Level Reasoning", "INNOVATION", "AI LEAP"),
    ("SPORTS", "Nepal Wins Crucial Cricket Match Against UAE by 7 Wickets", "CRICKET", "VICTORY"),
    ("ENTERTAINMENT", "Popular Film Star Wins Best Actor at International Awards", "AWARDS", "GLAMOUR"),
]

bg = "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=1080&h=1350&fit=crop"

print("Generating samples...")
for cat, hl, b1, b2 in samples:
    html = generate_news_card(hl, b1, b2, bg, cat, "This is a short summary that describes the news in one sentence for the image overlay.")
    fname = f"sample_{cat.lower()}.png"
    print(f" -> Generating {fname}")
    hti.screenshot(html_str=html, save_as=fname)

print("Done!")
