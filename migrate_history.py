import json
import os

def migrate_history(json_path, txt_path):
    if not os.path.exists(json_path):
        return
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return

    # For main.py history (list)
    if isinstance(data, list):
        with open(txt_path, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(f"{item.strip()}\n")
    
    # For wc_scores.py history (dict)
    elif isinstance(data, dict):
        with open(txt_path, 'w', encoding='utf-8') as f:
            for k, v in data.items():
                f.write(f"{k}:::{v}\n")
    
    print(f"Migrated {json_path} to {txt_path}")
    os.remove(json_path)

if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
    migrate_history("data/scraped_history.json", "data/scraped_history.txt")
    migrate_history("data/wc_posted_history.json", "data/wc_posted_history.txt")
