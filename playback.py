"""playback.py — Log replay viewer for NPC Sim v2.

Can be used as a standalone window launched from app.py, or run directly:
    python playback.py sim_log.jsonl
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import json
import os
import math
import time


# ── Colour helpers ─────────────────────────────────────────────────────────────

def _hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"


BG           = _hex(18, 18, 28)
PANEL_BG     = _hex(22, 22, 38)
GOOD_COL     = _hex(60, 200, 80)
EVIL_COL     = _hex(220, 60, 60)
DEAD_COL     = _hex(90, 90, 90)
TEXT_COL     = _hex(200, 200, 220)
HEADER_COL   = _hex(140, 140, 255)
ITEM_COL     = _hex(200, 180, 80)
SPEECH_COL   = _hex(255, 255, 140)
HP_FG        = _hex(60, 200, 60)
HP_LOW       = _hex(220, 60, 60)


class PlaybackViewer(ttk.Frame):
    """Embedded frame that can live in a Toplevel or standalone window."""

    CANVAS_W = 700
    CANVAS_H = 600
    PANEL_W  = 320

    def __init__(self, parent, log_path: str = None):
        super().__init__(parent)
        self.pack(fill=tk.BOTH, expand=True)

        self.turns: list[dict] = []
        self.header: dict = {}
        self._idx: int = 0
        self._playing: bool = False
        self._play_speed_ms: int = 1000
        self._selected_name: str | None = None

        self._build_ui()

        if log_path and os.path.exists(log_path):
            self._load(log_path)

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.configure(style="TFrame")

        # ── Top toolbar ───────────────────────────────────────────────────────
        tb = ttk.Frame(self)
        tb.pack(fill=tk.X, padx=6, pady=4)

        ttk.Button(tb, text="Open Log", command=self._open_log).pack(side=tk.LEFT, padx=3)
        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(tb, text="⏮",  command=self._go_first).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="◀◀", command=self._prev10).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="◀",  command=self._prev).pack(side=tk.LEFT, padx=2)
        self.btn_play = ttk.Button(tb, text="▶  Play", command=self._toggle_play)
        self.btn_play.pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="▶",  command=self._next).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="▶▶", command=self._next10).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="⏭",  command=self._go_last).pack(side=tk.LEFT, padx=2)
        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Label(tb, text="Speed:").pack(side=tk.LEFT)
        self.var_speed = tk.IntVar(value=1000)
        ttk.Spinbox(tb, from_=100, to=5000, increment=100,
                    textvariable=self.var_speed, width=6,
                    command=self._on_speed_change).pack(side=tk.LEFT, padx=3)
        ttk.Label(tb, text="ms/turn").pack(side=tk.LEFT)

        # ── Turn scrubber ──────────────────────────────────────────────────────
        sf = ttk.Frame(self)
        sf.pack(fill=tk.X, padx=6)
        self.var_turn = tk.IntVar(value=0)
        self._scrubber = ttk.Scale(sf, from_=0, to=1, variable=self.var_turn,
                                    orient=tk.HORIZONTAL, command=self._scrub)
        self._scrubber.pack(fill=tk.X, padx=4)
        self._turn_label = ttk.Label(sf, text="Turn 0 / 0")
        self._turn_label.pack(anchor="e", padx=8)

        # ── Main area ─────────────────────────────────────────────────────────
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Canvas
        self._canvas = tk.Canvas(main, width=self.CANVAS_W, height=self.CANVAS_H,
                                  bg=BG, cursor="crosshair")
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._canvas.bind("<Button-1>", self._on_canvas_click)

        # Right panel (inspector + log)
        rp = ttk.Frame(main, width=self.PANEL_W)
        rp.pack(side=tk.LEFT, fill=tk.BOTH, padx=(4, 0))
        rp.pack_propagate(False)

        ttk.Label(rp, text="Inspector", foreground=HEADER_COL,
                  font=("Consolas", 11, "bold")).pack(anchor="w", padx=6, pady=(4, 0))
        self._inspector = scrolledtext.ScrolledText(
            rp, height=18, width=38, bg=PANEL_BG, fg=TEXT_COL,
            font=("Consolas", 9), state=tk.DISABLED, relief=tk.FLAT, wrap=tk.WORD)
        self._inspector.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        ttk.Separator(rp, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=4)
        ttk.Label(rp, text="Turn Events", foreground=HEADER_COL,
                  font=("Consolas", 10, "bold")).pack(anchor="w", padx=6, pady=(4, 0))
        self._event_log = scrolledtext.ScrolledText(
            rp, height=10, width=38, bg=PANEL_BG, fg=TEXT_COL,
            font=("Consolas", 9), state=tk.DISABLED, relief=tk.FLAT, wrap=tk.WORD)
        self._event_log.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ── Meta info bar ──────────────────────────────────────────────────────
        mb = ttk.Frame(self)
        mb.pack(fill=tk.X, padx=6, pady=2)
        self._meta_label = ttk.Label(mb, text="No log loaded", foreground="#8888aa",
                                      font=("Consolas", 9))
        self._meta_label.pack(side=tk.LEFT)

    # ── Load ──────────────────────────────────────────────────────────────────

    def _open_log(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSONL", "*.jsonl"), ("All", "*.*")],
            title="Open simulation log",
        )
        if path:
            self._load(path)

    def _load(self, path: str):
        raw = SimLogger_load(path)
        self.header = {}
        self.turns = []
        for entry in raw:
            if entry.get("_type") == "header":
                self.header = entry
            elif entry.get("_type") == "turn" or "turn" in entry:
                self.turns.append(entry)

        if not self.turns:
            return

        self._idx = 0
        self._scrubber.config(to=max(1, len(self.turns) - 1))
        self.var_turn.set(0)

        seed = self.header.get("seed", "?")
        align = self.header.get("storyteller_alignment", "?")
        fname = os.path.basename(path)
        self._meta_label.config(
            text=f"{fname}  |  turns: {len(self.turns)}  |  seed: {seed}  |  alignment: {align}"
        )
        self._render_turn()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_first(self):
        self._set_idx(0)

    def _go_last(self):
        self._set_idx(len(self.turns) - 1)

    def _prev(self):
        self._set_idx(self._idx - 1)

    def _next(self):
        self._set_idx(self._idx + 1)

    def _prev10(self):
        self._set_idx(self._idx - 10)

    def _next10(self):
        self._set_idx(self._idx + 10)

    def _set_idx(self, idx: int):
        if not self.turns:
            return
        self._idx = max(0, min(len(self.turns) - 1, idx))
        self.var_turn.set(self._idx)
        self._render_turn()

    def _scrub(self, val):
        idx = int(float(val))
        if idx != self._idx:
            self._idx = idx
            self._render_turn()

    def _toggle_play(self):
        self._playing = not self._playing
        if self._playing:
            self.btn_play.config(text="⏸  Pause")
            self._auto_advance()
        else:
            self.btn_play.config(text="▶  Play")

    def _auto_advance(self):
        if not self._playing:
            return
        if self._idx < len(self.turns) - 1:
            self._set_idx(self._idx + 1)
            delay = max(100, self.var_speed.get())
            self.after(delay, self._auto_advance)
        else:
            self._playing = False
            self.btn_play.config(text="▶  Play")

    def _on_speed_change(self):
        self._play_speed_ms = self.var_speed.get()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_turn(self):
        if not self.turns:
            return
        turn_data = self.turns[self._idx]
        turn_num  = turn_data.get("turn", self._idx)
        total     = len(self.turns)
        self._turn_label.config(text=f"Turn {turn_num} / {total - 1}")

        world_size = self.header.get("world_size", 40)
        cw = self._canvas.winfo_width()  or self.CANVAS_W
        ch = self._canvas.winfo_height() or self.CANVAS_H
        scale = min(cw, ch) / (world_size + 2)

        def ws(wx, wy):
            return int(wx * scale + scale), int(wy * scale + scale)

        self._canvas.delete("all")

        # Grid
        for gx in range(0, world_size + 1, 5):
            sx, sy = ws(gx, 0)
            ex, ey = ws(gx, world_size)
            self._canvas.create_line(sx, sy, ex, ey, fill="#1e1e32")
        for gy in range(0, world_size + 1, 5):
            sx, sy = ws(0, gy)
            ex, ey = ws(world_size, gy)
            self._canvas.create_line(sx, sy, ex, ey, fill="#1e1e32")

        # Items
        for item in turn_data.get("items", []):
            ix, iy = ws(item["x"], item["y"])
            r = max(3, int(scale * 0.3))
            self._canvas.create_rectangle(ix-r, iy-r, ix+r, iy+r, fill=ITEM_COL, outline="")
            self._canvas.create_text(ix + r + 2, iy, text=item["name"][:18],
                                      fill="#c8b860", anchor="w", font=("Consolas", 8))

        # Characters
        known_evil = set(self.header.get("evil", []))
        for c in turn_data.get("characters", []):
            cx, cy = ws(c["x"], c["y"])
            is_dead = c.get("is_dead", False)
            is_evil = c.get("is_evil", False) or c["name"] in known_evil

            if is_dead:
                col = DEAD_COL
                self._canvas.create_polygon(
                    cx, cy-8, cx-6, cy+5, cx+6, cy+5,
                    fill=DEAD_COL, outline="#606060", width=1
                )
                self._canvas.create_text(cx + 10, cy, text=f"✝ {c['name'][:12]}",
                                          fill=DEAD_COL, anchor="w", font=("Consolas", 8))
                continue

            col = EVIL_COL if is_evil else GOOD_COL
            r = max(5, int(scale * 0.45))

            # Glow for selected
            if self._selected_name and c["name"] == self._selected_name:
                self._canvas.create_oval(cx-r-4, cy-r-4, cx+r+4, cy+r+4,
                                          fill="", outline="#ffffff", width=2)

            self._canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                      fill=col, outline="", width=0)

            # HP bar
            hp     = c.get("health", 100)
            max_hp = 100
            ratio  = max(0.0, hp / max_hp)
            bw = max(20, int(r * 2.5))
            self._canvas.create_rectangle(cx - bw//2, cy - r - 7,
                                           cx + bw//2, cy - r - 3,
                                           fill="#3a1010", outline="")
            bar_col = HP_FG if ratio > 0.35 else HP_LOW
            self._canvas.create_rectangle(cx - bw//2, cy - r - 7,
                                           cx - bw//2 + int(bw * ratio), cy - r - 3,
                                           fill=bar_col, outline="")
            # Name
            name_col = "#ff9999" if is_evil else "#99ffaa"
            self._canvas.create_text(cx + r + 3, cy - r//2,
                                      text=c["name"][:12],
                                      fill=name_col, anchor="w", font=("Consolas", 8))

        # Speeches
        for sp in turn_data.get("speeches", []):
            sx, sy = ws(sp["x"], sp["y"])
            self._canvas.create_text(sx, sy - 14, text=sp["text"][:45],
                                      fill=SPEECH_COL, font=("Consolas", 8),
                                      anchor="s")

        # Turn number overlay
        self._canvas.create_text(6, 6, text=f"Turn {turn_num}", fill="#9090cc",
                                   anchor="nw", font=("Consolas", 10, "bold"))

        # Situation
        situation = turn_data.get("global_situation") or ""
        if not situation and self.header:
            situation = ""
        if situation:
            self._canvas.create_text(cw//2, ch - 10, text=situation[:80],
                                      fill="#6688aa", font=("Consolas", 8), anchor="s")

        # Inspector / event log
        self._refresh_events(turn_data)
        if self._selected_name:
            c = next((c for c in turn_data.get("characters", [])
                      if c["name"] == self._selected_name), None)
            if c:
                self._refresh_inspector(c)

    def _refresh_inspector(self, c: dict):
        self._inspector.config(state=tk.NORMAL)
        self._inspector.delete("1.0", tk.END)
        lines = [
            f"Name:        {c['name']}",
            f"Status:      {'DEAD' if c.get('is_dead') else c.get('condition','—')}",
            f"HP:          {c.get('health','?')}",
            f"Position:    {c.get('x','?')},{c.get('y','?')}",
            f"Mood:        {c.get('mood','—')}",
            f"Personality: {c.get('personality','—')}",
            f"Is evil:     {c.get('is_evil', False)}",
            "",
            "── Goals ───────────────────────────────",
            f"Short-term:  {c.get('short_term_goal','—')}",
            f"Long-term:   {c.get('long_term_goal', c.get('motivation','—'))}",
            "",
            "── Inventory ───────────────────────────",
        ]
        inv = c.get("inventory", [])
        lines += [f"  · {i}" for i in inv] if inv else ["  (empty)"]
        lines += [
            "",
            "── Meters ──────────────────────────────",
            f"  Hunger: {int(c.get('hunger',0)*100)}%  "
            f"Fear: {int(c.get('fear',0)*100)}%",
            "",
            "── Relationships ───────────────────────",
            c.get("relationships") or c.get("relationship_summary") or "  None",
            "",
            "── Memory ──────────────────────────────",
            c.get("memory","(none)"),
        ]
        # Full memory if available
        fm = c.get("full_memory")
        if fm and isinstance(fm, dict):
            mono = fm.get("monologue", [])
            if mono:
                lines += ["", "── Monologue ────────────────────────────"]
                lines += [f"  {m}" for m in mono]
            sus = fm.get("suspicions", {})
            if sus:
                lines += ["", "── Suspicions ───────────────────────────"]
                for name, lvl in sorted(sus.items(), key=lambda x: -x[1]):
                    lines.append(f"  {name}: {'▮'*lvl}{'▯'*(10-lvl)} {lvl}/10")
            alliances = fm.get("alliances", [])
            if alliances:
                lines += ["", "── Alliances ────────────────────────────"]
                lines += [f"  ⚔ {a}" for a in alliances]

        self._inspector.insert(tk.END, "\n".join(str(l) for l in lines))
        self._inspector.config(state=tk.DISABLED)

    def _refresh_events(self, turn_data: dict):
        self._event_log.config(state=tk.NORMAL)
        self._event_log.delete("1.0", tk.END)
        events = turn_data.get("events", [])
        for ev in events:
            self._event_log.insert(tk.END, ev + "\n")
        self._event_log.see(tk.END)
        self._event_log.config(state=tk.DISABLED)

    def _on_canvas_click(self, event):
        if not self.turns:
            return
        turn_data = self.turns[self._idx]
        world_size = self.header.get("world_size", 40)
        cw = self._canvas.winfo_width() or self.CANVAS_W
        ch = self._canvas.winfo_height() or self.CANVAS_H
        scale = min(cw, ch) / (world_size + 2)

        def ws(wx, wy):
            return int(wx * scale + scale), int(wy * scale + scale)

        best, best_d = None, 30
        for c in turn_data.get("characters", []):
            cx, cy = ws(c["x"], c["y"])
            d = math.hypot(event.x - cx, event.y - cy)
            if d < best_d:
                best, best_d = c, d

        if best:
            self._selected_name = best["name"]
            self._refresh_inspector(best)
            self._render_turn()   # re-draw with selection highlight


# ── Helper: load log without importing SimLogger ─────────────────────────────

def SimLogger_load(path: str) -> list[dict]:
    turns = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    turns.append(json.loads(line))
                except Exception:
                    pass
    return turns


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    log_path = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    root.title("NPC Sim v2 — Playback Viewer")
    root.geometry("1080x720")
    PlaybackViewer(root, log_path)
    root.mainloop()
