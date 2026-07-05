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

    # 2. Run Main Content Engine
    print("\n[2/4] Running Main Engine (News, Gold, NASA, etc.)...")
    run_cmd("python main.py")

    # 3. Run Football Scores Engine
    print("\n[3/4] Running WC Scores Engine...")
    run_cmd("python wc_scores.py")

    # 4. Update Heartbeat
    if not os.path.exists("data"):
        os.makedirs("data")
    
    now_utc = datetime.now(timezone.utc)
    # Write ISO format timestamp
    with open("data/last_heartbeat.txt", "w") as f:
        f.write(now_utc.isoformat())

    # 5. Push updated state back to GitHub
    print("\n[4/4] Pushing updated state to GitHub...")
    run_cmd("git add data/scraped_history.txt data/wc_posted_history.txt data/last_heartbeat.txt")
    
    # Check if there are changes to commit
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True)
    if "data/" in status.stdout:
        run_cmd('git config user.name "github-actions[bot]"')
        run_cmd('git config user.email "github-actions[bot]@users.noreply.github.com"')
        run_cmd('git commit -m "chore: sync state from local device [skip ci]"')
        
        # Try to push, if it fails due to remote changes during our run, pull and push again
        push_res = run_cmd("git push")
        if push_res != 0:
            print("\n[!] Push failed. Remote changed. Rebasing and trying again...")
            run_cmd("git pull --rebase")
            run_cmd("git push")
    else:
        print("  [-] No state changes to push.")

    print("\n" + "="*60)
    print("  Sync Complete!")
    print("="*60)

if __name__ == "__main__":
    main()
