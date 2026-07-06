# -*- coding: utf-8 -*-
"""
NCN Dashboard Monitor
Click anywhere or press Refresh to update.
"""

import tkinter as tk
from tkinter import ttk
import os
import json
from datetime import datetime, timedelta, timezone

# ──────────────────────────────────────────────
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE  = os.path.join(SCRIPT_DIR, "data", "scraped_history.txt")
HEARTBEAT_FILE = os.path.join(SCRIPT_DIR, "data", "last_heartbeat.txt")
DASHBOARD_FILE = os.path.join(SCRIPT_DIR, "dashboard_stats.txt")
OUTPUT_DIR    = os.path.join(SCRIPT_DIR, "output")
POSTED_DIR    = os.path.join(SCRIPT_DIR, "output", "posted")

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
def count_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for l in f if l.strip())
    except Exception:
        return 0

def count_files(folder, ext=".png"):
    try:
        return sum(1 for f in os.listdir(folder) if f.endswith(ext))
    except Exception:
        return 0

def get_last_heartbeat():
    try:
        with open(HEARTBEAT_FILE, "r") as f:
            dt = datetime.fromisoformat(f.read().strip())
            nepal = dt + timedelta(hours=5, minutes=45)
            return nepal
    except Exception:
        return None

def get_nepal_now():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=45)

def get_next_run(last_hb):
    if last_hb:
        # Calculate next clock-aligned 15-minute interval relative to last_hb
        # Note: If it's been delayed, we calculate the next upcoming 15m mark relative to NOW
        now = get_nepal_now()
        next_min = ((now.minute // 15) + 1) * 15
        nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=next_min)
        
        diff = (nxt - now).total_seconds()
        m, s = divmod(int(diff), 60)
        return f"~{m}m {s}s", GREEN
    return "Unknown", DIM

def parse_dashboard():
    entries = []
    try:
        with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entries.append(line)
    except Exception:
        pass
    return entries

def get_current_data():
    total_posts   = count_lines(HISTORY_FILE)
    images_ready  = count_files(OUTPUT_DIR)
    images_posted = count_files(POSTED_DIR)
    last_hb       = get_last_heartbeat()
    next_str, next_clr = get_next_run(last_hb)
    history_entries = parse_dashboard()

    # Last run details from dashboard
    last_run_str = history_entries[-1] if history_entries else "No run recorded yet"

    return {
        "total_posts":    total_posts,
        "images_ready":   images_ready,
        "images_posted":  images_posted,
        "last_hb":        last_hb.strftime("%I:%M %p, %b %d") if last_hb else "N/A",
        "next_run":       next_str,
        "next_clr":       next_clr,
        "last_run":       last_run_str,
        "history":        history_entries,
    }

# ──────────────────────────────────────────────
# GUI
# ──────────────────────────────────────────────
class NCNDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NCN Monitor — Nepal Central News")
        self.geometry("820x680")
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
        tk.Label(hdr, text="  Monitor Dashboard",
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

        # ── Stat cards (top row) ──
        row1 = tk.Frame(self, bg=BG)
        row1.pack(fill="x", padx=20, pady=(0, 8))
        for i in range(4):
            row1.columnconfigure(i, weight=1)

        self.card_posts  = self._stat_card(row1, "Total Posts", "–", YELLOW, 0)
        self.card_ready  = self._stat_card(row1, "Images Ready", "–", ACCENT, 1)
        self.card_posted = self._stat_card(row1, "Images Posted", "–", GREEN, 2)
        self.card_pct    = self._stat_card(row1, "Posted %", "–", NEPSE_C, 3)

        # ── Last run & Next run ──
        row2 = tk.Frame(self, bg=BG)
        row2.pack(fill="x", padx=20, pady=(0, 8))
        row2.columnconfigure(0, weight=3)
        row2.columnconfigure(1, weight=2)

        # Last heartbeat card
        lhb = self._card(row2, col=0)
        tk.Label(lhb, text="🕑  Last Run", font=("Segoe UI", 9, "bold"),
                 fg=DIM, bg=CARD_BG).pack(anchor="w", padx=16, pady=(14, 2))
        self.lbl_last_hb = tk.Label(lhb, text="–",
                                    font=("Segoe UI", 13, "bold"), fg=TEXT, bg=CARD_BG)
        self.lbl_last_hb.pack(anchor="w", padx=16, pady=(0, 14))

        # Next run card
        nxt_card = self._card(row2, col=1)
        tk.Label(nxt_card, text="⏰  Next Scrape In", font=("Segoe UI", 9, "bold"),
                 fg=DIM, bg=CARD_BG).pack(anchor="w", padx=16, pady=(14, 2))
        self.lbl_next = tk.Label(nxt_card, text="–",
                                 font=("Consolas", 18, "bold"), fg=GREEN, bg=CARD_BG)
        self.lbl_next.pack(anchor="w", padx=16, pady=(0, 14))

        # ── Last run detail ──
        ld = tk.Frame(self, bg=BG)
        ld.pack(fill="x", padx=20, pady=(0, 8))
        ld_inner = tk.Frame(ld, bg=CARD_BG, padx=16, pady=12)
        ld_inner.pack(fill="x")
        tk.Label(ld_inner, text="📋  Last Run Detail",
                 font=("Segoe UI", 9, "bold"), fg=DIM, bg=CARD_BG).pack(anchor="w")
        self.lbl_last_detail = tk.Label(ld_inner, text="–",
                                        font=("Consolas", 9), fg=ACCENT, bg=CARD_BG,
                                        wraplength=760, justify="left")
        self.lbl_last_detail.pack(anchor="w", pady=(4, 0))

        # ── History log ──
        hf = tk.Frame(self, bg=BG)
        hf.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        tk.Label(hf, text="📜  Previous Run History  (auto-resets every 24h)",
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

        # History log
        self.txt_history.config(state="normal")
        self.txt_history.delete("1.0", "end")

        entries = d["history"]
        if not entries:
            self.txt_history.insert("end", "  No run history found yet. Waiting for first run…\n", "ts")
        else:
            for line in reversed(entries):  # newest first
                # Colour-code parts
                parts = line.split("|")
                for i, part in enumerate(parts):
                    part = part.strip()
                    if i == 0:
                        self.txt_history.insert("end", part + "  ", "ts")
                    elif "Local Laptop" in part:
                        self.txt_history.insert("end", "| " + part + "  ", "local")
                    elif "GitHub Cloud" in part:
                        self.txt_history.insert("end", "| " + part + "  ", "cloud")
                    else:
                        self.txt_history.insert("end", "| " + part + "  ", "kv")
                self.txt_history.insert("end", "\n")

        self.txt_history.config(state="disabled")

        # Status dot
        hb = d["last_hb"]
        self.status_dot.config(fg=GREEN if hb != "N/A" else RED)

        # Clock
        now = get_nepal_now()
        self.lbl_clock.config(
            text=f"Nepal Time: {now.strftime('%I:%M:%S %p, %b %d %Y')}   |   Scrapper Folder: {SCRIPT_DIR}"
        )

    def _auto_refresh(self):
        self.refresh()
        self.after(10000, self._auto_refresh)  # every 10 seconds


# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = NCNDashboard()
    app.mainloop()
