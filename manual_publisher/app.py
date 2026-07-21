import os
import sys
import uuid
import time
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

# Add the project root to sys.path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.renderer import render_html_card
from facebook.publisher import post_to_facebook

app = Flask(__name__)
# Configure upload folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'output', 'manual_uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

from flask import send_file
@app.route('/logo.png')
def serve_logo():
    return send_file(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'assets', 'logo.png')))

@app.route('/post', methods=['POST'])
def post_news():
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image uploaded'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'})
            
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type'})
            
        headline = request.form.get('headline', '')
        subtitle = request.form.get('subtitle', '')
        source = request.form.get('source', '')
        caption = request.form.get('caption', '')
        hashtags = request.form.get('hashtags', '#NepalCentralNews')
        # Template index: 0 means random (pick 1-16), else use specified template
        try:
            template_index = int(request.form.get('template_index', 0))
            if template_index == 0:
                import random
                template_index = random.randint(1, 16)
        except (ValueError, TypeError):
            template_index = 1
        
        # Save original uploaded image
        filename = secure_filename(file.filename)
        unique_prefix = str(uuid.uuid4())[:8]
        input_image_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{unique_prefix}_{filename}")
        file.save(input_image_path)
        
        # Render HTML Card
        rendered_output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"rendered_{unique_prefix}.jpg")
        
        # Determine category
        category = "Manual Post"
        
        success, result_path = render_html_card(
            image_path=input_image_path,
            category=category,
            headline=headline,
            subtitle=subtitle,
            output_path=rendered_output_path,
            index=template_index
        )
        
        if not success:
            return jsonify({'success': False, 'error': f'Template rendering failed: {result_path}'})
            
        # Post to Facebook
        article_dict = {
            'final_image_path': rendered_output_path,
            'english_description': caption,
            'source_name': source,
            'hashtags': hashtags.split(),
            'category': category
        }
        
        fb_success, fb_result = post_to_facebook(article_dict)
        
        if fb_success:
            return jsonify({'success': True, 'post_id': fb_result})
        else:
            return jsonify({'success': False, 'error': f'Facebook upload failed: {fb_result}'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download', methods=['POST'])
def download_news():
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image uploaded'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'})
            
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type'})
            
        headline = request.form.get('headline', '')
        subtitle = request.form.get('subtitle', '')
        source = request.form.get('source', '')
        
        try:
            template_index = int(request.form.get('template_index', 0))
            if template_index == 0:
                import random
                template_index = random.randint(1, 16)
        except (ValueError, TypeError):
            template_index = 1
        
        filename = secure_filename(file.filename)
        unique_prefix = str(uuid.uuid4())[:8]
        input_image_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{unique_prefix}_{filename}")
        file.save(input_image_path)
        
        rendered_output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"rendered_{unique_prefix}.jpg")
        category = "Manual Post"
        
        success, result_path = render_html_card(
            image_path=input_image_path,
            category=category,
            headline=headline,
            subtitle=subtitle,
            output_path=rendered_output_path,
            index=template_index
        )
        
        if not success:
            return jsonify({'success': False, 'error': f'Template rendering failed: {result_path}'})
            
        return send_file(rendered_output_path, as_attachment=True, download_name='NCN_Poster.jpg')
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("Starting Manual Publisher UI...")
    # Run on all interfaces so it can be accessed from phone on the same network if needed
    # debug=False prevents the server from auto-restarting and dropping the connection when an image is saved
    app.run(host='0.0.0.0', port=5000, debug=False)
