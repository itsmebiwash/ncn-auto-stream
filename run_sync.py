import subprocess
import time
import os
import sys
from datetime import datetime, timezone, timedelta

# Fix Unicode issues in Windows console
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(SCRIPT_DIR, "data", "scraped_history.txt")
DASHBOARD_FILE = os.path.join(SCRIPT_DIR, "dashboard_stats.txt")

def run_cmd(cmd, check=False):
    print(f"\n> {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=SCRIPT_DIR)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if check and result.returncode != 0:
        print(f"[!] Command failed with code {result.returncode}")
    return result.returncode

def count_history_lines():
    """Count lines in scraped_history.txt as a proxy for total posts ever."""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return sum(1 for l in f if l.strip())
    except Exception:
        pass
    return 0

def get_nepal_time_str():
    nepal_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=45)
    return nepal_now.strftime("%Y-%m-%d %I:%M %p")

def write_dashboard(env_str, duration, posts_before, posts_after, had_new_state):
    posts_this_run = max(0, posts_after - posts_before)
    
    # Calculate next clock-aligned 15-minute interval (Task Scheduler behavior)
    now = datetime.now()
    next_min = ((now.minute // 15) + 1) * 15
    next_run_dt = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=next_min)
    next_run_str = next_run_dt.strftime("%I:%M %p")

    # Reset if older than 24h
    if os.path.exists(DASHBOARD_FILE):
        if time.time() - os.path.getmtime(DASHBOARD_FILE) > 86400:
            os.remove(DASHBOARD_FILE)

    line = (
        f"[{get_nepal_time_str()}] "
        f"Source: {env_str} | "
        f"Duration: {duration:.0f}s | "
        f"Posts this run: {posts_this_run} | "
        f"Total posts (all-time): {posts_after} | "
        f"State synced: {'YES' if had_new_state else 'NO'} | "
        f"Next scrap: ~{next_run_str}\n"
    )

    with open(DASHBOARD_FILE, "a", encoding="utf-8") as f:
        f.write(line)

    print(f"\n  [Dashboard] {line.strip()}")
    print(f"  [Next run] ~{next_run_str}")

def main():
    start_time = time.time()
    env_str = "GitHub Cloud" if os.environ.get("GITHUB_ACTIONS") == "true" else "Local Laptop"

    print("=" * 60)
    print(f"  NCN Auto-Sync & Run Wrapper  [{env_str}]")
    print(f"  Nepal Time: {get_nepal_time_str()}")
    print("=" * 60)

    # 0. GitHub Actions: check heartbeat — skip if laptop is active
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("\n[0/5] Checking last heartbeat...")
        hb_path = os.path.join(SCRIPT_DIR, "data", "last_heartbeat.txt")
        if os.path.exists(hb_path):
            try:
                with open(hb_path, "r") as f:
                    last_time = datetime.fromisoformat(f.read().strip())
                diff_minutes = (datetime.now(timezone.utc) - last_time).total_seconds() / 60.0
                print(f"  Last heartbeat: {diff_minutes:.1f} min ago.")
                if diff_minutes < 25:
                    print("  [OK] Local device is active! GitHub skipping run.")
                    return
            except Exception:
                pass

    # 1. Pull latest state
    print("\n[1/5] Syncing state from GitHub...")
    run_cmd("git pull --rebase")

    # Snapshot history count BEFORE running
    posts_before = count_history_lines()

    # 2. Claim heartbeat lock
    print("\n[2/5] Claiming execution lock...")
    data_dir = os.path.join(SCRIPT_DIR, "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    with open(os.path.join(data_dir, "last_heartbeat.txt"), "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())

    run_cmd("git add data/last_heartbeat.txt")
    status_chk = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True, cwd=SCRIPT_DIR)
    if "last_heartbeat.txt" in status_chk.stdout:
        run_cmd('git config user.name "github-actions[bot]"')
        run_cmd('git config user.email "github-actions[bot]@users.noreply.github.com"')
        run_cmd('git commit -m "chore: claim execution lock [skip ci]"')
        run_cmd("git push")

    # 3. Main Content Engine
    print("\n[3/5] Running Main Engine (News, Gold, NASA, NEPSE etc.)...")
    run_cmd(f'"{SCRIPT_DIR}\\..".replace("..","")')  # cd safety
    run_cmd("python main.py")

    # 4. Football/WC Scores Engine
    print("\n[4/5] Running WC Scores Engine...")
    run_cmd("python wc_scores.py")

    # 5. Push updated state
    print("\n[5/5] Pushing state to GitHub...")
    # Only add files that actually exist
    git_add_files = ["data/scraped_history.txt", "data/wc_posted_history.txt"]
    if os.path.exists(os.path.join(SCRIPT_DIR, "data", "wc_posted_history.json")):
        git_add_files.append("data/wc_posted_history.json")
    run_cmd("git add " + " ".join(git_add_files))
    
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True, cwd=SCRIPT_DIR)
    had_new_state = "data/" in status.stdout

    if had_new_state:
        run_cmd('git commit -m "chore: sync state from local device [skip ci]"')
        push_res = run_cmd("git push")
        if push_res != 0:
            print("\n[!] Push failed. Rebasing...")
            run_cmd("git pull --rebase")
            run_cmd("git push")
    else:
        print("  [-] No new state to push.")

    # Snapshot history count AFTER
    posts_after = count_history_lines()

    # 6. Write Dashboard Stats
    duration = time.time() - start_time
    write_dashboard(env_str, duration, posts_before, posts_after, had_new_state)

    print("\n" + "=" * 60)
    print("  Sync Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
