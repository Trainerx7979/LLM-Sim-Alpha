"""main.py — Entry point for NPC Simulation v2.

Usage:
    python main.py                    # Launch TkInter control panel + Pygame window
    python main.py --play sim_log.jsonl   # Open playback viewer directly
    python main.py --headless             # Run sim without GUI (logs only)
    python main.py --seed 12345           # Pre-set seed
"""

import argparse
import sys
import random


def main():
    parser = argparse.ArgumentParser(description="NPC Simulation v2")
    parser.add_argument("--play",     metavar="LOG",  help="Open log in playback viewer")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--seed",     type=int, default=None, help="Random seed")
    parser.add_argument("--count",    type=int, default=None, help="Number of characters")
    parser.add_argument("--alignment", default=None, help="Storyteller alignment")
    args = parser.parse_args()

    # ── Playback-only mode ─────────────────────────────────────────────────────
    if args.play:
        import tkinter as tk
        from playback import PlaybackViewer
        root = tk.Tk()
        root.title(f"NPC Sim v2 — Playback: {args.play}")
        root.geometry("1100x740")
        PlaybackViewer(root, args.play)
        root.mainloop()
        return

    # ── Headless mode ─────────────────────────────────────────────────────────
    if args.headless:
        _run_headless(args)
        return

    # ── Full GUI mode ──────────────────────────────────────────────────────────
    import tkinter as tk
    from app import App
    import config

    root = App()
    root.geometry("640x680")

    # Apply CLI overrides
    if args.seed is not None:
        root.var_seed.set(str(args.seed))
    if args.count is not None:
        root.var_char_count.set(args.count)
    if args.alignment:
        root.var_alignment.set(args.alignment)

    root.mainloop()


def _run_headless(args):
    """Run the simulation loop with no GUI, printing to stdout."""
    import time
    import config
    from simulation import Simulation, SimState

    seed = args.seed or random.randint(0, 2 ** 31)
    count = args.count or config.DEFAULT_CHARACTER_COUNT
    alignment = args.alignment or config.DEFAULT_ALIGNMENT

    print(f"[Headless] seed={seed}  count={count}  alignment={alignment}")

    state = SimState()
    sim   = Simulation(state)
    sim.start(seed=seed, count=count, alignment=alignment)

    try:
        while sim.is_running():
            snap = state.snapshot()
            if snap["victory"]:
                print(f"[Headless] Victory: {snap['victory']}")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Headless] Interrupted.")
    finally:
        sim.stop()
        print("[Headless] Done.")


if __name__ == "__main__":
    main()
