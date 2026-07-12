# -*- coding: utf-8 -*-
"""
NCN Dashboard Monitor
Click anywhere or press Refresh to update.
"""

import tkinter as tk
from tkinter import ttk
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from database.db_client import get_db

# ──────────────────────────────────────────────
SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR     = os.path.join(SCRIPT_DIR, "output")
POSTED_DIR     = os.path.join(SCRIPT_DIR, "output", "posted")

# Colours
BG       = "#0d0f14"
CARD_BG  = "#13161e"
ACCENT   = "#00e5ff"
GREEN    = "#00e676"
YELLOW   = "#ffd600"
RED      = "#ff3d00"
TEXT     = "#e0e8ff"
DIM      = "#4a5568"
WHITE    = "#ffffff"
NEPSE_C  = "#7c4dff"

# ──────────────────────────────────────────────
# DATA HELPERS
# ──────────────────────────────────────────────
def is_scrapper_running():
    """Detect run_scraper.py or run_worker.py using PowerShell."""
    try:
        cmd = (
            'Get-WmiObject Win32_Process -Filter "name=\'python.exe\'" | '
            'Select-Object -ExpandProperty CommandLine'
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            stderr=subprocess.DEVNULL, timeout=8
        ).decode("utf-8", "ignore")
        return "run_pipeline.py" in out.lower()
    except Exception:
        return False


def start_scrapper():
    if is_scrapper_running():
        return False
    try:
        # Start python run_pipeline.py in background without creating a visible window
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            [sys.executable, "run_pipeline.py"], 
            cwd=SCRIPT_DIR,
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception as e:
        print(f"Failed to start: {e}")
        return False


def stop_scrapper():
    try:
        cmd = 'Get-WmiObject Win32_Process -Filter "name=\'python.exe\'" | ForEach-Object { if ($_.CommandLine -like "*run_pipeline.py*") { Stop-Process $_.ProcessId -Force } }'
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, check=False)
        return True
    except Exception:
        return False


def get_nepal_now():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=45)


def get_current_data():
    try:
        db = get_db()
        total_posts = db.articles.count_documents({"status": "posted"})
        images_ready = db.articles.count_documents({"status": "queued"})
        images_posted = total_posts
        
        hb = db.telemetry.find_one({"device": "laptop"})
        last_hb = None
        if hb:
            last_hb = hb["last_active"]
            if last_hb.tzinfo is None:
                last_hb = last_hb.replace(tzinfo=timezone.utc)
            last_hb = last_hb + timedelta(hours=5, minutes=45) # Nepal offset
            
        next_str = "Active" if is_scrapper_running() else "Stopped"
        next_clr = GREEN if is_scrapper_running() else RED
        
        # Fetch recent posts from MongoDB
        history_entries = []
        recent = list(db.articles.find({"status": "posted"}).sort([("posted_at", -1)]).limit(15))
        for art in recent:
            posted_at = art.get("posted_at")
            if posted_at:
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
                nepal_time = (posted_at + timedelta(hours=5, minutes=45)).strftime("%I:%M %p")
            else:
                nepal_time = "N/A"
            title = art.get("english_headline", "No Headline")[:45] + "..."
            history_entries.append(f"[{nepal_time}] | Posted | {title} | source: {art.get('source_name', 'Unknown')}")
            
        last_run_str = f"Last Post: {recent[0].get('english_headline', 'No headline')[:50]}..." if total_posts > 0 else "No post history found"
        
        return {
            "total_posts": total_posts,
            "images_ready": images_ready,
            "images_posted": images_posted,
            "videos_ready": 0,
            "videos_posted": 0,
            "last_hb": last_hb.strftime("%I:%M %p, %b %d") if last_hb else "N/A",
            "next_run": next_str,
            "next_clr": next_clr,
            "last_run": last_run_str,
            "history": history_entries,
        }
    except Exception as e:
        print(f"[Dashboard Data Error] {e}")
        return {
            "total_posts": 0, "images_ready": 0, "images_posted": 0,
            "videos_ready": 0, "videos_posted": 0, "last_hb": "N/A",
            "next_run": "Error", "next_clr": RED, "last_run": "Database offline", "history": []
        }

# ──────────────────────────────────────────────
# GUI
# ──────────────────────────────────────────────
class NCNDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NCN Monitor — Nepal Central News")
        self.geometry("900x760")
        self.minsize(700, 580)
        self.configure(bg=BG)
        self.resizable(True, True)

        # Custom style
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("TScrollbar", background=DIM, troughcolor=BG, bordercolor=BG, arrowcolor=TEXT)

        self._build_ui()
        self.refresh()
        self._auto_refresh()

    # ── Layout ────────────────────────────────
    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self, bg=BG, pady=12)
        hdr.pack(fill="x", padx=20)
        tk.Label(hdr, text="NCN", font=("Consolas", 22, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(hdr, text="  Monitor Dashboard (MongoDB)",
                 font=("Segoe UI", 16, "bold"), fg=TEXT, bg=BG).pack(side="left")

        # Refresh + Status
        right = tk.Frame(hdr, bg=BG)
        right.pack(side="right")
        self.status_dot = tk.Label(right, text="●", font=("Segoe UI", 18),
                                   fg=GREEN, bg=BG)
        self.status_dot.pack(side="right", padx=(4, 0))
        tk.Button(right, text="⟳ Refresh",
                  font=("Segoe UI", 10, "bold"),
                  bg=ACCENT, fg=BG, relief="flat", padx=12, pady=5,
                  cursor="hand2", command=self.refresh).pack(side="right")
        self.btn_start = tk.Button(right, text="▶ Start Bot",
                                   font=("Segoe UI", 10, "bold"), bg=GREEN, fg=BG,
                                   relief="flat", padx=12, pady=5, cursor="hand2",
                                   command=self.start_clicked)
        self.btn_start.pack(side="right", padx=(6, 0))
        self.btn_stop = tk.Button(right, text="■ Stop Bot",
                                  font=("Segoe UI", 10, "bold"), bg=RED, fg=WHITE,
                                  relief="flat", padx=12, pady=5, cursor="hand2",
                                  command=self.stop_clicked)
        self.btn_stop.pack(side="right", padx=(6, 0))

        # ── Stat cards (top row) ──
        row1 = tk.Frame(self, bg=BG)
        row1.pack(fill="x", padx=20, pady=(0, 8))
        for i in range(4):
            row1.columnconfigure(i, weight=1)

        self.card_posts  = self._stat_card(row1, "Total Posts", "–", YELLOW, 0)
        self.card_ready  = self._stat_card(row1, "Queued Posts", "–", ACCENT, 1)
        self.card_posted = self._stat_card(row1, "Images Posted", "–", GREEN, 2)
        self.card_pct    = self._stat_card(row1, "Upload %", "–", NEPSE_C, 3)

        row1b = tk.Frame(self, bg=BG)
        row1b.pack(fill="x", padx=20, pady=(0, 8))
        for i in range(4):
            row1b.columnconfigure(i, weight=1)
        self.card_vready = self._stat_card(row1b, "Videos Ready", "0", ACCENT, 0)
        self.card_vposted = self._stat_card(row1b, "Videos Posted", "0", GREEN, 1)
        self.card_running = self._stat_card(row1b, "Local Engine Status", "–", YELLOW, 2)
        self.card_mode = self._stat_card(row1b, "Mode", "MongoDB", NEPSE_C, 3)

        # ── Last run & Next run ──
        row2 = tk.Frame(self, bg=BG)
        row2.pack(fill="x", padx=20, pady=(0, 8))
        row2.columnconfigure(0, weight=3)
        row2.columnconfigure(1, weight=2)

        # Last heartbeat card
        lhb = self._card(row2, col=0)
        tk.Label(lhb, text="🕑  Last Laptop Heartbeat", font=("Segoe UI", 9, "bold"),
                 fg=DIM, bg=CARD_BG).pack(anchor="w", padx=16, pady=(14, 2))
        self.lbl_last_hb = tk.Label(lhb, text="–",
                                    font=("Segoe UI", 13, "bold"), fg=TEXT, bg=CARD_BG)
        self.lbl_last_hb.pack(anchor="w", padx=16, pady=(0, 14))

        # Next run card
        nxt_card = self._card(row2, col=1)
        tk.Label(nxt_card, text="⏰  Local Engine State", font=("Segoe UI", 9, "bold"),
                 fg=DIM, bg=CARD_BG).pack(anchor="w", padx=16, pady=(14, 2))
        self.lbl_next = tk.Label(nxt_card, text="–",
                                 font=("Consolas", 18, "bold"), fg=GREEN, bg=CARD_BG)
        self.lbl_next.pack(anchor="w", padx=16, pady=(0, 14))

        # ── Last run detail ──
        ld = tk.Frame(self, bg=BG)
        ld.pack(fill="x", padx=20, pady=(0, 8))
        ld_inner = tk.Frame(ld, bg=CARD_BG, padx=16, pady=12)
        ld_inner.pack(fill="x")
        tk.Label(ld_inner, text="📋  Last Posted News",
                 font=("Segoe UI", 9, "bold"), fg=DIM, bg=CARD_BG).pack(anchor="w")
        self.lbl_last_detail = tk.Label(ld_inner, text="–",
                                        font=("Consolas", 9), fg=ACCENT, bg=CARD_BG,
                                        wraplength=840, justify="left")
        self.lbl_last_detail.pack(anchor="w", pady=(4, 0))

        # ── History log ──
        hf = tk.Frame(self, bg=BG)
        hf.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        tk.Label(hf, text="📜  Recent MongoDB Post History",
                 font=("Segoe UI", 9, "bold"), fg=DIM, bg=BG).pack(anchor="w", pady=(0, 4))

        txt_frame = tk.Frame(hf, bg=CARD_BG, bd=0)
        txt_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(txt_frame, style="TScrollbar")
        scrollbar.pack(side="right", fill="y")

        self.txt_history = tk.Text(txt_frame, bg=CARD_BG, fg=TEXT,
                                   font=("Consolas", 9), relief="flat",
                                   state="disabled", yscrollcommand=scrollbar.set,
                                   padx=12, pady=8, wrap="none", height=10,
                                   cursor="arrow", insertbackground=BG)
        self.txt_history.pack(fill="both", expand=True)
        scrollbar.config(command=self.txt_history.yview)

        # Colour tags for history
        self.txt_history.tag_configure("ts",    foreground=DIM)
        self.txt_history.tag_configure("local", foreground=GREEN)
        self.txt_history.tag_configure("cloud", foreground=ACCENT)
        self.txt_history.tag_configure("kv",    foreground=YELLOW)

        # ── Footer clock ──
        self.lbl_clock = tk.Label(self, text="", font=("Consolas", 9),
                                  fg=DIM, bg=BG)
        self.lbl_clock.pack(pady=(0, 8))

    # ── Helpers ───────────────────────────────
    def _card(self, parent, col):
        f = tk.Frame(parent, bg=CARD_BG, padx=0, pady=0)
        f.grid(row=0, column=col, padx=(0, 8), sticky="nsew", ipady=4)
        return f

    def _stat_card(self, parent, title, value, color, col):
        f = tk.Frame(parent, bg=CARD_BG)
        f.grid(row=0, column=col, padx=(0, 8) if col < 3 else 0, sticky="nsew", ipady=4)
        tk.Label(f, text=title, font=("Segoe UI", 9, "bold"),
                 fg=DIM, bg=CARD_BG).pack(anchor="w", padx=16, pady=(12, 2))
        lbl = tk.Label(f, text=value, font=("Segoe UI", 26, "bold"),
                       fg=color, bg=CARD_BG)
        lbl.pack(anchor="w", padx=16, pady=(0, 12))
        return lbl

    # ── Refresh ───────────────────────────────
    def refresh(self):
        d = get_current_data()

        # Stat cards
        total = d["total_posts"]
        posted = d["images_posted"]
        ready  = d["images_ready"]
        pct = f"{int(posted/(ready+posted)*100)}%" if (ready + posted) > 0 else "0%"

        self.card_posts.config(text=str(total))
        self.card_ready.config(text=str(ready))
        self.card_posted.config(text=str(posted))
        self.card_pct.config(text=pct)

        # Last run / next run
        self.lbl_last_hb.config(text=d["last_hb"])
        self.lbl_next.config(text=d["next_run"], fg=d["next_clr"])
        self.lbl_last_detail.config(text=d["last_run"])

        running = is_scrapper_running()
        self.card_running.config(text="Running" if running else "Stopped")
        self.card_running.config(fg=GREEN if running else RED)
        self.btn_start.config(state="disabled" if running else "normal")
        self.btn_stop.config(state="normal" if running else "disabled")
        self.card_vready.config(text=str(d["videos_ready"]))
        self.card_vposted.config(text=str(d["videos_posted"]))

        # History log
        self.txt_history.config(state="normal")
        self.txt_history.delete("1.0", "end")

        entries = d["history"]
        if not entries:
            self.txt_history.insert("end", "  No run history found yet. Waiting for first run…\n", "ts")
        else:
            for line in entries:  # newest first (from DB)
                self.txt_history.insert("end", line + "\n", "ts")

        self.txt_history.config(state="disabled")

        # Status dot
        self.status_dot.config(fg=GREEN if running else RED)

        # Clock
        now = get_nepal_now()
        self.lbl_clock.config(
            text=f"Nepal Time: {now.strftime('%I:%M:%S %p, %b %d %Y')}   |   Scrapper Folder: {SCRIPT_DIR}"
        )

    def start_clicked(self):
        ok = start_scrapper()
        self.refresh()
        if ok:
            self.lbl_last_detail.config(text="Started scraper & worker processes in background.")

    def stop_clicked(self):
        ok = stop_scrapper()
        self.refresh()
        if ok:
            self.lbl_last_detail.config(text="Force stopped local scraper & worker background scripts.")

    def _auto_refresh(self):
        self.refresh()
        self.after(5000, self._auto_refresh)  # every 5 seconds


# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = NCNDashboard()
    app.mainloop()
