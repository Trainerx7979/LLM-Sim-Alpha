"""app.py — TkInter control panel for NPC Sim v2.

Runs in the main thread.  Launches the Pygame renderer and simulation
in daemon threads.  Provides full configuration, save/load, playback.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import json
import random
import queue
import os
import time

import config
from simulation import Simulation, SimState
from renderer import Renderer
from logger import SimLogger


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NPC Simulation v2 — Control Panel")
        self.resizable(True, True)
        self.configure(bg="#12121c")

        # ── Shared state ───────────────────────────────────────────────────────
        self.sim_state = SimState()
        self.simulation = Simulation(self.sim_state)
        self.renderer_cmd_queue: queue.Queue = queue.Queue()
        self.renderer = Renderer(self.sim_state, command_queue=self.renderer_cmd_queue)

        # ── Tk variables ───────────────────────────────────────────────────────
        self.var_seed         = tk.StringVar(value="")
        self.var_char_count   = tk.IntVar(value=config.DEFAULT_CHARACTER_COUNT)
        self.var_alignment    = tk.StringVar(value=config.DEFAULT_ALIGNMENT)
        self.var_world_size   = tk.IntVar(value=config.DEFAULT_WORLD_SIZE)
        self.var_speed        = tk.DoubleVar(value=0.5)
        self.var_zoom         = tk.DoubleVar(value=config.DEFAULT_ZOOM)
        self.var_log_file     = tk.StringVar(value=config.LOG_FILE)
        self.var_status       = tk.StringVar(value="Ready")
        self.var_model        = tk.StringVar(value=config.OLLAMA_MODEL)
        self.var_ollama_url   = tk.StringVar(value=config.OLLAMA_API_URL)

        self._build_ui()
        self._start_ui_updater()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame",       background="#1a1a2e")
        style.configure("TLabel",       background="#1a1a2e", foreground="#d0d0e8", font=("Consolas", 10))
        style.configure("TButton",      font=("Consolas", 10), padding=4)
        style.configure("TEntry",       fieldbackground="#23233a", foreground="#e8e8f0")
        style.configure("TCombobox",    fieldbackground="#23233a", foreground="#e8e8f0")
        style.configure("TScale",       background="#1a1a2e", troughcolor="#23233a")
        style.configure("Header.TLabel", font=("Consolas", 11, "bold"), foreground="#8888ff",
                        background="#1a1a2e")
        style.configure("Status.TLabel", font=("Consolas", 10), foreground="#88ff88",
                        background="#0e0e1c")
        style.configure("Accent.TButton", font=("Consolas", 11, "bold"),
                        foreground="#ffffff", background="#334")

        # ── Root notebook ──────────────────────────────────────────────────────
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        tab_sim  = ttk.Frame(nb)
        tab_cfg  = ttk.Frame(nb)
        tab_char = ttk.Frame(nb)
        tab_log  = ttk.Frame(nb)

        nb.add(tab_sim,  text="  Simulation  ")
        nb.add(tab_cfg,  text="  Configuration  ")
        nb.add(tab_char, text="  Characters  ")
        nb.add(tab_log,  text="  Log  ")

        self._build_sim_tab(tab_sim)
        self._build_cfg_tab(tab_cfg)
        self._build_char_tab(tab_char)
        self._build_log_tab(tab_log)

        # ── Status bar ─────────────────────────────────────────────────────────
        status_bar = ttk.Label(self, textvariable=self.var_status,
                               style="Status.TLabel", anchor="w", padding=(6, 2))
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    # ────────────────────────────────────────────────────────────────────────────
    #  Simulation tab
    # ────────────────────────────────────────────────────────────────────────────

    def _build_sim_tab(self, parent):
        parent.configure(style="TFrame")
        pad = {"padx": 8, "pady": 4}

        ttk.Label(parent, text="NPC Simulation v2", style="Header.TLabel").pack(**pad)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, **pad)

        self.btn_start = ttk.Button(btn_frame, text="▶  Start",  command=self._start_sim,
                                     style="Accent.TButton")
        self.btn_pause = ttk.Button(btn_frame, text="⏸  Pause",  command=self._toggle_pause,
                                     state=tk.DISABLED)
        self.btn_stop  = ttk.Button(btn_frame, text="⏹  Stop",   command=self._stop_sim,
                                     state=tk.DISABLED)

        for b in (self.btn_start, self.btn_pause, self.btn_stop):
            b.pack(side=tk.LEFT, padx=4, pady=2)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=6)

        # Speed
        sf = ttk.Frame(parent)
        sf.pack(fill=tk.X, **pad)
        ttk.Label(sf, text="Sim Speed (delay):").pack(side=tk.LEFT)
        ttk.Scale(sf, from_=0.0, to=5.0, variable=self.var_speed,
                  orient=tk.HORIZONTAL, length=200,
                  command=self._on_speed_change).pack(side=tk.LEFT, padx=6)
        ttk.Label(sf, textvariable=tk.StringVar()).pack(side=tk.LEFT)  # placeholder
        self._speed_label = ttk.Label(sf, text="0.5 s")
        self._speed_label.pack(side=tk.LEFT)

        # Zoom
        zf = ttk.Frame(parent)
        zf.pack(fill=tk.X, **pad)
        ttk.Label(zf, text="Zoom:           ").pack(side=tk.LEFT)
        ttk.Scale(zf, from_=config.MIN_ZOOM, to=config.MAX_ZOOM,
                  variable=self.var_zoom, orient=tk.HORIZONTAL, length=200,
                  command=self._on_zoom_change).pack(side=tk.LEFT, padx=6)
        self._zoom_label = ttk.Label(zf, text="1.0×")
        self._zoom_label.pack(side=tk.LEFT)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=6)

        # Project save/load
        pf = ttk.Frame(parent)
        pf.pack(fill=tk.X, **pad)
        ttk.Label(pf, text="Project:").pack(side=tk.LEFT)
        ttk.Button(pf, text="Save", command=self._save_project).pack(side=tk.LEFT, padx=3)
        ttk.Button(pf, text="Load", command=self._load_project).pack(side=tk.LEFT, padx=3)

        # Log file
        lf = ttk.Frame(parent)
        lf.pack(fill=tk.X, **pad)
        ttk.Label(lf, text="Log file:").pack(side=tk.LEFT)
        ttk.Entry(lf, textvariable=self.var_log_file, width=26).pack(side=tk.LEFT, padx=4)
        ttk.Button(lf, text="Browse", command=self._browse_log).pack(side=tk.LEFT)
        ttk.Button(lf, text="📂 Open Playback",
                   command=self._open_playback).pack(side=tk.LEFT, padx=6)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=6)

        # Live turn / character info
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill=tk.BOTH, expand=True, **pad)
        ttk.Label(info_frame, text="Live Info", style="Header.TLabel").pack(anchor="w")
        self._info_text = tk.Text(info_frame, height=10, width=52,
                                   bg="#0e0e1c", fg="#b0b0cc",
                                   font=("Consolas", 9), state=tk.DISABLED,
                                   relief=tk.FLAT)
        self._info_text.pack(fill=tk.BOTH, expand=True)

    # ────────────────────────────────────────────────────────────────────────────
    #  Configuration tab
    # ────────────────────────────────────────────────────────────────────────────

    def _build_cfg_tab(self, parent):
        parent.configure(style="TFrame")
        pad = {"padx": 10, "pady": 4}

        ttk.Label(parent, text="Simulation Configuration", style="Header.TLabel").pack(**pad)

        def row(label, widget_builder):
            f = ttk.Frame(parent)
            f.pack(fill=tk.X, **pad)
            ttk.Label(f, text=label, width=22, anchor="e").pack(side=tk.LEFT)
            widget_builder(f).pack(side=tk.LEFT, padx=6)

        row("Random seed:",
            lambda f: ttk.Entry(f, textvariable=self.var_seed, width=16))
        row("Character count:",
            lambda f: ttk.Spinbox(f, from_=2, to=20, textvariable=self.var_char_count,
                                   width=6))
        row("World size:",
            lambda f: ttk.Spinbox(f, from_=20, to=80, textvariable=self.var_world_size,
                                   width=6))
        row("Storyteller alignment:",
            lambda f: ttk.Combobox(f, textvariable=self.var_alignment,
                                    values=config.STORYTELLER_ALIGNMENTS,
                                    width=16, state="readonly"))
        row("Ollama model:",
            lambda f: ttk.Entry(f, textvariable=self.var_model, width=20))
        row("Ollama URL:",
            lambda f: ttk.Entry(f, textvariable=self.var_ollama_url, width=36))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(parent, text=(
            "Seed: leave blank for random.\n"
            "Same seed + same model = deterministic replay.\n"
            "Alignment: neutral | benevolent | malevolent | chaotic | scientific"
        ), justify=tk.LEFT, foreground="#7070a0").pack(padx=10, anchor="w")

        ttk.Button(parent, text="Apply LLM settings",
                   command=self._apply_llm_settings).pack(padx=10, pady=8, anchor="w")

    # ────────────────────────────────────────────────────────────────────────────
    #  Characters tab
    # ────────────────────────────────────────────────────────────────────────────

    def _build_char_tab(self, parent):
        parent.configure(style="TFrame")
        pad = {"padx": 8, "pady": 4}

        ttk.Label(parent, text="Character Inspector", style="Header.TLabel").pack(**pad)

        # Listbox of character names
        lf = ttk.Frame(parent)
        lf.pack(fill=tk.BOTH, expand=True, **pad)

        scrollbar = ttk.Scrollbar(lf, orient=tk.VERTICAL)
        self._char_listbox = tk.Listbox(lf, yscrollcommand=scrollbar.set,
                                         bg="#0e0e1c", fg="#c0d0c0",
                                         selectbackground="#334488",
                                         font=("Consolas", 10), height=8)
        scrollbar.config(command=self._char_listbox.yview)
        self._char_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)
        self._char_listbox.bind("<<ListboxSelect>>", self._on_char_select)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=4)

        # Detail view
        detail_frame = ttk.Frame(parent)
        detail_frame.pack(fill=tk.BOTH, expand=True, **pad)
        ttk.Label(detail_frame, text="Details", style="Header.TLabel").pack(anchor="w")
        self._char_detail = tk.Text(detail_frame, height=16, width=52,
                                     bg="#0e0e1c", fg="#c8c8e8",
                                     font=("Consolas", 9), state=tk.DISABLED,
                                     relief=tk.FLAT, wrap=tk.WORD)
        self._char_detail.pack(fill=tk.BOTH, expand=True)

    # ────────────────────────────────────────────────────────────────────────────
    #  Log tab
    # ────────────────────────────────────────────────────────────────────────────

    def _build_log_tab(self, parent):
        parent.configure(style="TFrame")
        pad = {"padx": 8, "pady": 4}
        ttk.Label(parent, text="Simulation Log", style="Header.TLabel").pack(**pad)

        self._log_text = scrolledtext.ScrolledText(
            parent, height=25, bg="#0a0a14", fg="#b0c0b0",
            font=("Consolas", 9), state=tk.DISABLED, relief=tk.FLAT)
        self._log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        bf = ttk.Frame(parent)
        bf.pack(fill=tk.X, **pad)
        ttk.Button(bf, text="Clear",       command=self._clear_log).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Save to file",command=self._export_log).pack(side=tk.LEFT, padx=3)
        self._autoscroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(bf, text="Auto-scroll", variable=self._autoscroll).pack(side=tk.LEFT, padx=6)

    # ── Button callbacks ───────────────────────────────────────────────────────

    def _start_sim(self):
        if self.simulation.is_running():
            messagebox.showinfo("Already running", "Stop the current simulation first.")
            return

        # Apply LLM settings before starting
        self._apply_llm_settings()

        seed_txt = self.var_seed.get().strip()
        seed = int(seed_txt) if seed_txt.isdigit() else None
        if seed is None:
            seed = random.randint(0, 2**31)
            self.var_seed.set(str(seed))

        count     = self.var_char_count.get()
        alignment = self.var_alignment.get()
        wsize     = self.var_world_size.get()
        log_file  = self.var_log_file.get().strip() or config.LOG_FILE

        # Start Pygame renderer first
        if not self.renderer.is_running():
            self.renderer.start()
            time.sleep(0.3)

        # Start simulation
        self.simulation.start(
            seed=seed,
            count=count,
            alignment=alignment,
            world_size=wsize,
            log_file=log_file,
        )
        self.sim_state.speed_delay = self.var_speed.get()

        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL)
        self.var_status.set(f"Running — seed {seed}  alignment: {alignment}")

    def _toggle_pause(self):
        if self.sim_state.paused:
            self.simulation.resume()
            self.btn_pause.config(text="⏸  Pause")
            self.var_status.set("Running…")
        else:
            self.simulation.pause()
            self.btn_pause.config(text="▶  Resume")
            self.var_status.set("Paused")

    def _stop_sim(self):
        self.simulation.stop()
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED, text="⏸  Pause")
        self.btn_stop.config(state=tk.DISABLED)
        self.var_status.set("Stopped")

    def _on_speed_change(self, val):
        v = round(float(val), 1)
        self._speed_label.config(text=f"{v} s")
        self.sim_state.speed_delay = v

    def _on_zoom_change(self, val):
        v = round(float(val), 1)
        self._zoom_label.config(text=f"{v}×")
        self.renderer_cmd_queue.put({"type": "set_zoom", "value": v})

    def _apply_llm_settings(self):
        config.OLLAMA_MODEL   = self.var_model.get().strip()
        config.OLLAMA_API_URL = self.var_ollama_url.get().strip()

    # ── Save / load project ────────────────────────────────────────────────────

    def _save_project(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            title="Save Project",
        )
        if not path:
            return
        proj = {
            "seed":       self.var_seed.get(),
            "char_count": self.var_char_count.get(),
            "alignment":  self.var_alignment.get(),
            "world_size": self.var_world_size.get(),
            "speed":      self.var_speed.get(),
            "log_file":   self.var_log_file.get(),
            "model":      self.var_model.get(),
            "ollama_url": self.var_ollama_url.get(),
        }
        with open(path, "w") as f:
            json.dump(proj, f, indent=2)
        self.var_status.set(f"Project saved: {os.path.basename(path)}")

    def _load_project(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")], title="Load Project",
        )
        if not path:
            return
        try:
            with open(path) as f:
                proj = json.load(f)
            self.var_seed.set(proj.get("seed", ""))
            self.var_char_count.set(proj.get("char_count", config.DEFAULT_CHARACTER_COUNT))
            self.var_alignment.set(proj.get("alignment", config.DEFAULT_ALIGNMENT))
            self.var_world_size.set(proj.get("world_size", config.DEFAULT_WORLD_SIZE))
            self.var_speed.set(proj.get("speed", 0.5))
            self.var_log_file.set(proj.get("log_file", config.LOG_FILE))
            self.var_model.set(proj.get("model", config.OLLAMA_MODEL))
            self.var_ollama_url.set(proj.get("ollama_url", config.OLLAMA_API_URL))
            self.var_status.set(f"Project loaded: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def _browse_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".jsonl",
            filetypes=[("JSONL", "*.jsonl"), ("All", "*.*")],
            title="Choose log file",
        )
        if path:
            self.var_log_file.set(path)

    def _open_playback(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSONL", "*.jsonl"), ("All", "*.*")],
            title="Open log for playback",
        )
        if path:
            _launch_playback(path)

    # ── Log tab ────────────────────────────────────────────────────────────────

    def _clear_log(self):
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.config(state=tk.DISABLED)

    def _export_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
        )
        if path:
            content = self._log_text.get("1.0", tk.END)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.var_status.set(f"Log exported: {os.path.basename(path)}")

    # ── Character tab ──────────────────────────────────────────────────────────

    def _on_char_select(self, event):
        sel = self._char_listbox.curselection()
        if not sel:
            return
        name = self._char_listbox.get(sel[0])
        chars = self.sim_state.characters + self.sim_state.dead_characters
        npc = next((c for c in chars if c.name == name.lstrip("✝ ")), None)
        if not npc:
            return
        # Set as selected in renderer
        with self.sim_state._lock:
            self.sim_state.selected_npc = npc
        self._refresh_char_detail(npc)

    def _refresh_char_detail(self, npc):
        detail = self._char_detail
        detail.config(state=tk.NORMAL)
        detail.delete("1.0", tk.END)
        lines = [
            f"Name:        {npc.name}",
            f"Status:      {'DEAD' if npc.is_dead else npc.condition}",
            f"HP:          {npc.health}/{npc.max_health}",
            f"Position:    {npc.x},{npc.y}",
            f"Mood:        {npc.mood}",
            f"Personality: {npc.personality}",
            f"Motivation:  {npc.motivation}",
            f"Is evil:     {npc.is_evil}",
            "",
            "── Goals ───────────────────────────────",
            f"Short-term:  {npc.short_term_goal or '—'}",
            f"Long-term:   {npc.long_term_goal or '—'}",
            "",
            "── Inventory ───────────────────────────",
        ]
        lines += [f"  · {i}" for i in npc.inventory] or ["  (empty)"]
        lines += [
            "",
            "── Meters ──────────────────────────────",
            f"  Hunger: {int(npc.hunger*100)}%  Fear: {int(npc.fear_level*100)}%  Curiosity: {int(npc.curiosity*100)}%",
            "",
            "── Relationships ───────────────────────",
            npc.memory_system.get_relationship_summary() or "  None yet",
            "",
            "── Memory (top 8) ──────────────────────",
            npc.memory_system.get_summary(8),
            "",
            "── Internal Monologue ──────────────────",
            npc.memory_system.get_monologue_summary(5) or "  (silent)",
        ]
        detail.insert(tk.END, "\n".join(lines))
        detail.config(state=tk.DISABLED)

    # ── UI updater ─────────────────────────────────────────────────────────────

    def _start_ui_updater(self):
        self._update_ui()

    def _update_ui(self):
        snap = self.sim_state.snapshot()
        turn = snap["turn"]
        chars = snap["characters"]
        dead  = snap["dead_characters"]
        log_lines = snap["log_lines"]

        # Status
        if snap["victory"]:
            winner = "EVIL" if snap["victory"] == "evil" else "GOOD"
            self.var_status.set(f"★ {winner} WINS — Turn {turn}")
            if self.simulation.is_running():
                pass  # let the thread wind down naturally
        elif self.sim_state.running:
            self.var_status.set(
                f"Running — Turn {turn}  |  Alive: {len(chars)}  |  Dead: {len(dead)}"
            )

        # Live info text (Simulation tab)
        self._info_text.config(state=tk.NORMAL)
        self._info_text.delete("1.0", tk.END)
        for c in chars:
            evil_tag = " [EVIL]" if c.is_evil else ""
            hp_bar = "█" * int(c.health / 10) + "░" * (10 - int(c.health / 10))
            self._info_text.insert(tk.END,
                f"{c.name:<14}{evil_tag:<8} HP [{hp_bar}] {c.health:>3}  mood: {c.mood}\n")
        if dead:
            self._info_text.insert(tk.END, "\n── Deceased ──\n")
            for c in dead:
                self._info_text.insert(tk.END, f"  ✝ {c.name}\n")
        self._info_text.config(state=tk.DISABLED)

        # Character listbox
        names_alive = [c.name for c in chars]
        names_dead  = ["✝ " + c.name for c in dead]
        current = list(self._char_listbox.get(0, tk.END))
        new_list = names_alive + names_dead
        if current != new_list:
            self._char_listbox.delete(0, tk.END)
            for n in names_alive:
                self._char_listbox.insert(tk.END, n)
            for n in names_dead:
                self._char_listbox.insert(tk.END, n)

        # Log tab
        new_lines = log_lines[len(self._log_text.get("1.0", tk.END).splitlines()):]
        if new_lines:
            self._log_text.config(state=tk.NORMAL)
            self._log_text.insert(tk.END, "\n".join(new_lines) + "\n")
            if self._autoscroll.get():
                self._log_text.see(tk.END)
            self._log_text.config(state=tk.DISABLED)

        self.after(500, self._update_ui)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_close(self):
        self.simulation.stop()
        self.renderer.stop()
        self.destroy()


# ── Playback launcher ─────────────────────────────────────────────────────────

def _launch_playback(log_path: str):
    """Open the standalone playback viewer in a new Toplevel window."""
    from playback import PlaybackViewer
    win = tk.Toplevel()
    win.title(f"Playback — {os.path.basename(log_path)}")
    PlaybackViewer(win, log_path)
