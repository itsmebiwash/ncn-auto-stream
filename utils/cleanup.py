import os
import time
import glob

def run_cleanup():
    """
    Deletes images (.jpg) and videos (.mp4) in the output folder that are older than 60 minutes.
    """
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    if not os.path.exists(output_dir):
        return

    now = time.time()
    cutoff = now - 3600 # 60 minutes

    for ext in ["*.jpg", "*.mp4"]:
        pattern = os.path.join(output_dir, ext)
        for filepath in glob.glob(pattern):
            try:
                if os.path.isfile(filepath):
                    file_mtime = os.path.getmtime(filepath)
                    if file_mtime < cutoff:
                        os.remove(filepath)
                        print(f"[Cleanup] Deleted old file: {filepath}")
            except Exception as e:
                print(f"[Cleanup Error] Could not delete {filepath}: {e}")
