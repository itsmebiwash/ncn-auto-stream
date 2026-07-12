import os
import base64
from html2image import Html2Image

def render_html_card(image_path, category, headline, subtitle, output_path):
    """
    Renders the news card using HTML2Image.
    """
    try:
        # Load the template
        template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "news_template.html")
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Convert local image to base64 to avoid Chrome local file restriction
        with open(image_path, "rb") as img_file:
            img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
        
        # Detect extension
        ext = "jpeg" if image_path.lower().endswith("jpg") or image_path.lower().endswith("jpeg") else "png"
        img_data_uri = f"data:image/{ext};base64,{img_b64}"

        # Replace placeholders
        html_content = html_content.replace("{IMAGE_URL}", img_data_uri)
        html_content = html_content.replace("{CATEGORY_BADGE}", category)
        html_content = html_content.replace("{HEADLINE_TITLE}", headline)
        html_content = html_content.replace("{BODY_DESCRIPTION}", subtitle)
        
        # Handle the logo path by embedding it as well (optional, but safer)
        logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as logo_file:
                logo_b64 = base64.b64encode(logo_file.read()).decode('utf-8')
                logo_data_uri = f"data:image/png;base64,{logo_b64}"
                # The template has <img src="../../assets/logo.png" ...>
                html_content = html_content.replace("../../assets/logo.png", logo_data_uri)

        # Render using HTML2Image
        hti = Html2Image(size=(1080, 1350))
        
        # html2image saves to the current working directory by default, so we extract filename and move it
        output_dir = os.path.dirname(output_path)
        output_filename = os.path.basename(output_path)
        
        hti.output_path = output_dir
        hti.screenshot(html_str=html_content, save_as=output_filename)
        
        return True, output_path
    except Exception as e:
        print(f"[HTML2Image Render Error] {e}")
        return False, str(e)
