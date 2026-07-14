import os
import requests
from io import BytesIO
from PIL import Image

def optimize_image(image_url_or_path, output_path, max_size_kb=500, target_size=(1200, 630), check_dimensions=False):
    """
    Downloads/loads an image, resizes it to target_size if provided,
    and compresses it to be under max_size_kb.
    If check_dimensions=True, rejects images that look like logos/banners.
    Saves the final image as JPEG.
    """
    try:
        if image_url_or_path.startswith("http"):
            response = requests.get(image_url_or_path, timeout=10)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
        else:
            img = Image.open(image_url_or_path)
            
        if check_dimensions:
            # 1. Check URL for ad/logo/banner keywords
            bad_keywords = ['logo', 'banner', 'ad', 'sponsor', 'promo', 'sidebar', 'footer', 'header', 'icon', 'avatar', 'ads', 'advertise', 'placeholder', 'default', 'og-image', 'brand', 'watermark']
            url_lower = image_url_or_path.lower()
            if any(word in url_lower for word in bad_keywords):
                return False, f"Image URL contains blocked keyword"
                
            # 1.5 Check raw file size (logos are usually tiny, < 15KB)
            if image_url_or_path.startswith("http"):
                if len(response.content) < 15360:
                    return False, f"Image rejected as logo/placeholder (too small: {len(response.content)} bytes)"

            # 2. Check dimensions
            w, h = img.size
            if w == 0 or h == 0:
                return False, "Invalid image dimensions"
            aspect = w / h
            # Reject if width < 500 or height < 400 or extreme aspect ratio
            if w < 500 or h < 400 or aspect > 2.2 or aspect < 0.6:
                return False, f"Image rejected as logo/banner/poster (w:{w}, h:{h}, aspect:{aspect:.2f})"

        # Convert to RGB to ensure JPEG compatibility
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        # Resize if target_size is given
        if target_size:
            # Resize using LANCZOS for high quality
            img = img.resize(target_size, Image.Resampling.LANCZOS)
        
        quality = 95
        step = 5
        
        while quality > 10:
            img.save(output_path, format="JPEG", quality=quality, optimize=True)
            size_kb = os.path.getsize(output_path) / 1024
            
            if size_kb <= max_size_kb:
                break
                
            quality -= step
            
        return True, output_path
        
    except Exception as e:
        print(f"[Image Optimization Error] {e}")
        return False, str(e)

def fetch_pexels_image(keywords, api_key):
    """
    Fetches a fallback image from Pexels API based on keywords.
    """
    if not api_key:
        return None
        
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": api_key}
    
    query = " ".join(keywords)
    params = {"query": query, "per_page": 1, "orientation": "landscape"}
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("photos"):
            return data["photos"][0]["src"]["large"]
    except Exception as e:
        print(f"[Pexels Fetch Error] {e}")
        
    return None
