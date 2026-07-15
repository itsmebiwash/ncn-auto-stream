import os
import base64
from datetime import datetime

def _resolve_template(article_index: int, template_dir: str) -> str:
    """
    Returns the absolute path to a template file sequentially (template_01.html ... template_16.html).
    """
    template_num = ((article_index - 1) % 16) + 1
    template_file = f"template_{template_num:02d}.html"
    template_path = os.path.join(template_dir, template_file)

    if not os.path.exists(template_path):
        # Last resort fallback if template renaming hasn't happened or file is missing
        template_path = os.path.join(template_dir, 'news_template.html')

    return template_path


def render_html_card(image_path: str, category: str, headline: str,
                     subtitle: str, output_path: str, index: int = 1):
    """
    Renders a 1080×1350 news card using HTML2Image.
    Selects the correct template based on the AI-detected article category.

    Returns (True, output_path) on success, (False, error_str) on failure.
    """
    try:
        template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
        template_path = _resolve_template(index, template_dir)

        with open(template_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Embed background image as base64 to avoid Chrome local file restrictions
        with open(image_path, 'rb') as img_file:
            img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
        ext = 'jpeg' if image_path.lower().endswith(('jpg', 'jpeg')) else 'png'
        img_data_uri = f'data:image/{ext};base64,{img_b64}'

        # Embed logo
        logo_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'logo.png')
        logo_data_uri = ''
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as lf:
                logo_data_uri = f'data:image/png;base64,{base64.b64encode(lf.read()).decode("utf-8")}'

        # Replace all known placeholder variants
        replacements = {
            '{IMAGE_URL}':        img_data_uri,
            '{CATEGORY_BADGE}':   'UPDATE:',
            '{HEADLINE_TITLE}':   headline,
            '{BODY_DESCRIPTION}': subtitle,
            '{BRAND_LOGO_URL}':   logo_data_uri,
            '{SOURCE_TEXT}':      '',
            '{DATE_TEXT}':        datetime.now().strftime('%B %d, %Y'),
            '../../assets/logo.png': logo_data_uri,
            '{{ SOURCE_TEXT }}':  '',
        }
        for placeholder, value in replacements.items():
            html_content = html_content.replace(placeholder, value)

        # Render with html2image
        from html2image import Html2Image
        hti = Html2Image(
            size=(1080, 1350),
            custom_flags=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--hide-scrollbars']
        )
        output_dir      = os.path.dirname(os.path.abspath(output_path))
        output_filename = os.path.basename(output_path)
        hti.output_path = output_dir
        hti.screenshot(html_str=html_content, save_as=output_filename)

        # CRITICAL: html2image can silently fail (Chromium crash/timeout) without
        # raising an exception. Verify the file was actually written to disk.
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
            return False, f'html2image produced no output at {output_path}'

        return True, output_path

    except Exception as e:
        print(f'[HTML2Image Render Error] {e}')
        return False, str(e)
