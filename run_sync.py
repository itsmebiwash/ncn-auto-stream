import subprocess
import time
import os
from datetime import datetime, timezone

def run_cmd(cmd, check=False):
    print(f"\n> {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if check and result.returncode != 0:
        print(f"[!] Command failed with code {result.returncode}")
    return result.returncode

def main():
    print("="*60)
    print("  NCN Auto-Sync & Run Wrapper")
    print("="*60)

    # 0. If running on GitHub Actions, check heartbeat to save minutes
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("\n[0/4] Checking last heartbeat...")
        if os.path.exists("data/last_heartbeat.txt"):
            with open("data/last_heartbeat.txt", "r") as f:
                last_time_str = f.read().strip()
                try:
                    last_time = datetime.fromisoformat(last_time_str)
                    now_utc = datetime.now(timezone.utc)
                    diff_minutes = (now_utc - last_time).total_seconds() / 60.0
                    print(f"  [-] Last heartbeat was {diff_minutes:.1f} minutes ago.")
                    if diff_minutes < 25:
                        print("  [✓] Local device is active! Skipping GitHub run to save minutes.")
                        return
                except Exception:
                    pass

    # 1. Pull latest state from GitHub to avoid posting duplicates
    print("\n[1/4] Syncing state from GitHub...")
    run_cmd("git pull --rebase")

    # 2. CLAIM THE LOCK: Update Heartbeat and push immediately so other devices don't start
    print("\n[2/4] Claiming execution lock (updating heartbeat)...")
    if not os.path.exists("data"):
        os.makedirs("data")
    now_utc = datetime.now(timezone.utc)
    with open("data/last_heartbeat.txt", "w") as f:
        f.write(now_utc.isoformat())
    
    run_cmd("git add data/last_heartbeat.txt")
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True)
    if "data/last_heartbeat.txt" in status.stdout:
        run_cmd('git config user.name "github-actions[bot]"')
        run_cmd('git config user.email "github-actions[bot]@users.noreply.github.com"')
        run_cmd('git commit -m "chore: claim execution lock [skip ci]"')
        run_cmd("git push")

    # 3. Run Main Content Engine
    print("\n[3/4] Running Main Engine (News, Gold, NASA, etc.)...")
    run_cmd("python main.py")

    # 4. Run Football Scores Engine
    print("\n[4/4] Running WC Scores Engine...")
    run_cmd("python wc_scores.py")

    # 5. Push updated state back to GitHub
    print("\n[5/5] Pushing updated history to GitHub...")
    run_cmd("git add data/scraped_history.txt data/wc_posted_history.txt")
    
    # Check if there are changes to commit
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True)
    
    posts_made = status.stdout.count('scraped_history.txt') + status.stdout.count('wc_posted_history.txt')
    if "data/" in status.stdout:
        run_cmd('git commit -m "chore: sync state from local device [skip ci]"')
        
        # Try to push, if it fails due to remote changes during our run, pull and push again
        push_res = run_cmd("git push")
        if push_res != 0:
            print("\n[!] Push failed. Remote changed. Rebasing and trying again...")
            run_cmd("git pull --rebase")
            run_cmd("git push")
    else:
        print("  [-] No state changes to push.")

    # 6. Log Dashboard Stats
    end_time = time.time()
    duration = end_time - start_time
    env_str = "GitHub Cloud" if os.environ.get("GITHUB_ACTIONS") == "true" else "Local Laptop"
    log_file = "dashboard_stats.txt"
    
    # Check if we need to reset the log (older than 24h)
    if os.path.exists(log_file):
        mod_time = os.path.getmtime(log_file)
        if time.time() - mod_time > 86400: # 24 hours
            os.remove(log_file)
            
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %I:%M %p')}] Ran on: {env_str} | Duration: {duration:.1f}s | State Changed: {'Yes' if 'data/' in status.stdout else 'No'}\n")
        
    print("\n" + "="*60)
    print("  Sync Complete!")
    print("="*60)

if __name__ == "__main__":
    start_time = time.time()
    main()
