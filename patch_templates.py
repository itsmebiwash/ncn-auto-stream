import os
import re
import glob

templates_dir = "templates"
html_files = sorted(glob.glob(os.path.join(templates_dir, "*.html")))

hashtag_pattern = re.compile(r'(<div class="hashtag-bar">)[^<]*(</div>)')

# Make sure we only process exactly 16 files, or at least up to 16
for i, filepath in enumerate(html_files):
    if i >= 16:
        break
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace hashtag
    content = hashtag_pattern.sub(r'\1#NCN\2', content)
    
    # Rename to template_01.html ... template_16.html
    new_filename = f"template_{i+1:02d}.html"
    new_filepath = os.path.join(templates_dir, new_filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
        
    os.rename(filepath, new_filepath)
    print(f"Renamed {os.path.basename(filepath)} -> {new_filename}")
