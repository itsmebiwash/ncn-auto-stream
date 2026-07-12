import os
import base64
from datetime import datetime

# Map category names that don't have their own template to the closest match
_CATEGORY_TEMPLATE_MAP = {
    # Direct matches (template file exists)
    'politics':       'Politics.html',
    'crime':          'Politics.html',   # Crime → Politics template (closest)
    'business':       'Business.html',
    'sports':         'Sports.html',
    'health':         'Health.html',
    'technology':     'Technology.html',
    'education':      'Education.html',
    'entertainment':  'Entertainment.html',
    'international':  'International.html',
    'environment':    'Enviroment.html',  # Note: typo in actual filename
    'science':        'Science.html',
    'lifestyle':      'lifestyle.html',
    'weather':        'Weather.html',
    'opinion':        'Opinion.html',
    'local':          'Local.html',
    'general':        'news_template.html',
}

_FALLBACK_TEMPLATE = 'news_template.html'


def _resolve_template(category: str, template_dir: str) -> str:
    """
    Returns the absolute path to the best-matching template file.
    Falls back to news_template.html if the category template is missing.
    """
    cat_key = category.strip().lower()
    template_file = _CATEGORY_TEMPLATE_MAP.get(cat_key, _FALLBACK_TEMPLATE)
    template_path = os.path.join(template_dir, template_file)

    if not os.path.exists(template_path):
        # Last resort fallback
        template_path = os.path.join(template_dir, _FALLBACK_TEMPLATE)

    return template_path


def render_html_card(image_path: str, category: str, headline: str,
                     subtitle: str, output_path: str):
    """
    Renders a 1080×1350 news card using HTML2Image.
    Selects the correct template based on the AI-detected article category.

    Returns (True, output_path) on success, (False, error_str) on failure.
    """
    try:
        template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
        template_path = _resolve_template(category, template_dir)

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
            '{CATEGORY_BADGE}':   category,
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
        hti = Html2Image(size=(1080, 1350))
        output_dir      = os.path.dirname(os.path.abspath(output_path))
        output_filename = os.path.basename(output_path)
        hti.output_path = output_dir
        hti.screenshot(html_str=html_content, save_as=output_filename)

        return True, output_path

    except Exception as e:
        print(f'[HTML2Image Render Error] {e}')
        return False, str(e)
