"""logger.py — JSONL simulation logger for NPC Sim v2"""

import json
import os
import time
import config


class SimLogger:
    """Writes one JSONL entry per turn.  Compatible with the old viewer
    schema while adding extended fields (seed, alignment, goals, mood, etc.)
    """

    def __init__(self, filename: str = config.LOG_FILE,
                 seed: int | None = None,
                 alignment: str = config.DEFAULT_ALIGNMENT,
                 world_size: int = config.DEFAULT_WORLD_SIZE):
        self.filename = filename
        self.seed = seed
        self.alignment = alignment
        self.world_size = world_size
        self._turn_data: dict | None = None
        self._header_written = False

    # ── Session header ─────────────────────────────────────────────────────────

    def write_header(self, characters, extra: dict | None = None):
        """Write a one-line session header (not a turn) at the top of the log."""
        header = {
            "_type": "header",
            "seed": self.seed,
            "storyteller_alignment": self.alignment,
            "world_size": self.world_size,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "characters": [c.name for c in characters],
            "evil": [c.name for c in characters if c.is_evil],
        }
        if extra:
            header.update(extra)
        self._write(header)
        self._header_written = True

    # ── Per-turn API ───────────────────────────────────────────────────────────

    def start_turn(self, turn: int):
        self._turn_data = {
            "_type": "turn",
            "turn": turn,
            "events": [],
            "characters": [],
            "speeches": [],
            "items": [],
            "seed": self.seed,
            "alignment": self.alignment,
        }

    def event(self, text: str):
        if self._turn_data is not None:
            self._turn_data["events"].append(str(text))

    def finalize(self, npcs, speeches, items=None):
        if self._turn_data is None:
            return

        for c in npcs:
            entry = {
                # ── Old schema (keep for backward-compat viewer) ──────────────
                "name": c.name,
                "x": c.x,
                "y": c.y,
                "health": c.health,
                "motivation": getattr(c, "motivation", ""),
                "personality": getattr(c, "personality", ""),
                "memory": c.memory_system.get_summary(8),
                # ── Extended fields ───────────────────────────────────────────
                "mood": getattr(c, "mood", "calm"),
                "condition": getattr(c, "condition", "Healthy"),
                "inventory": list(getattr(c, "inventory", [])),
                "short_term_goal": getattr(c, "short_term_goal", ""),
                "long_term_goal": getattr(c, "long_term_goal", ""),
                "hunger": round(getattr(c, "hunger", 0.0), 2),
                "fear": round(getattr(c, "fear_level", 0.0), 2),
                "is_evil": c.is_evil,
                "is_dead": getattr(c, "is_dead", False),
                "relationships": c.memory_system.get_relationship_summary(),
                "full_memory": c.memory_system.to_dict(),
            }
            self._turn_data["characters"].append(entry)

        for s in speeches:
            self._turn_data["speeches"].append({
                "speaker": s.source.name,
                "text": s.text,
                "x": s.source.x,
                "y": s.source.y,
                "target": s.target,
            })

        if items:
            for i in items:
                self._turn_data["items"].append(i.to_dict())

        self._write(self._turn_data)
        self._turn_data = None

    # ── Load for playback ─────────────────────────────────────────────────────

    @staticmethod
    def load(filename: str) -> list[dict]:
        turns = []
        if not os.path.exists(filename):
            return turns
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return turns

    # ── Private ───────────────────────────────────────────────────────────────

    def _write(self, obj: dict):
        with open(self.filename, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj) + "\n")
