import os
import glob

def replace_in_files():
    for filepath in glob.glob('**/*.py', recursive=True):
        if 'venv' in filepath or '__pycache__' in filepath:
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = content.replace('database.db_client', 'database.db_client')
        
        if content != new_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'Updated {filepath}')

if __name__ == '__main__':
    replace_in_files()
