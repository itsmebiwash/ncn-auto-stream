import os
import glob

def replace_in_files():
    for filepath in glob.glob('**/*.py', recursive=True):
        if 'venv' in filepath or '__pycache__' in filepath:
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replacements
        new_content = content.replace('from job_queue ', 'from job_queue ')
        new_content = new_content.replace('from job_queue.', 'from job_queue.')
        new_content = new_content.replace('import job_queue.', 'import job_queue.')
        new_content = new_content.replace('from database.', 'from database.')
        new_content = new_content.replace('from database ', 'from database ')
        new_content = new_content.replace('import database.', 'import database.')
        
        if content != new_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'Updated {filepath}')

if __name__ == '__main__':
    replace_in_files()
