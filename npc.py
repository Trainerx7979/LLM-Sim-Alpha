"""npc.py — NPC class for NPC Sim v2"""

import math
from memory import EnhancedMemorySystem
import config


class NPC:
    """An autonomous agent in the simulation."""

    def __init__(self, name, x, y, motivation, personality, health,
                 inventory, is_evil=False):
        # ── Core identity ──────────────────────────────────────────────────────
        self.name: str = name
        self.x: int = x
        self.y: int = y
        self.motivation: str = motivation
        self.personality: str = personality
        self.health: int = health
        self.max_health: int = health
        self.inventory: list[str] = list(inventory) if inventory else []
        self.condition: str = "Healthy"

        # ── AI state ───────────────────────────────────────────────────────────
        self.is_evil: bool = is_evil
        self.is_dead: bool = False
        self.last_dialogue: str = ""
        self.last_action: str = ""

        # ── Extended NPC attributes ────────────────────────────────────────────
        self.mood: str = "calm"
        self.short_term_goal: str = ""
        self.long_term_goal: str = motivation   # seeded from motivation
        self.hunger: float = 0.0     # 0‑1; grows each turn
        self.fear_level: float = 0.0
        self.curiosity: float = 0.5

        # ── Memory ─────────────────────────────────────────────────────────────
        self.memory_system: EnhancedMemorySystem = EnhancedMemorySystem()

        # ── Vision / hearing ──────────────────────────────────────────────────
        if is_evil and config.EVIL_ADVANTAGE:
            self.vision_range: int = config.EVIL_VISION_RANGE
        else:
            self.vision_range: int = config.HEARING_RANGE

        # ── Evil-specific overrides ────────────────────────────────────────────
        if self.is_evil:
            self.personality = "Ruthless"
            self.motivation = (
                "You are a psychopath. You brought everyone here to hunt them. "
                "You want to kill everyone one by one. You are the only one who knows this."
            )

        # ── Rendering hints ───────────────────────────────────────────────────
        self.sprite_name: str = name          # used to look up sprite file
        self.anim_frame: int = 0
        self.anim_timer: float = 0.0

    # ── Convenience ────────────────────────────────────────────────────────────

    def __repr__(self):
        role = " [EVIL]" if self.is_evil else ""
        return f"{self.name}{role} @{self.x},{self.y} HP:{self.health}"

    def can_hear(self, speech) -> bool:
        """Return True if this NPC is within earshot of a speech object."""
        d = math.hypot(self.x - speech.source.x, self.y - speech.source.y)
        if speech.target and speech.target == self.name:
            return True
        return d <= self.vision_range

    def can_see(self, other) -> bool:
        """Return True if this NPC can see another NPC."""
        dx = self.x - other.x
        dy = self.y - other.y
        return (dx * dx + dy * dy) <= (self.vision_range ** 2)

    def remember(self, text, category="observation", priority=1,
                 emotion=None, related_character=None):
        """Shorthand: add a memory via the memory system."""
        self.memory_system.add_memory(
            text, category=category, priority=priority,
            emotion=emotion, related_character=related_character,
        )
        # Mirror mood into NPC top-level field
        self.mood = self.memory_system.mood
        self.fear_level = self.memory_system.fear
        self.hunger = self.memory_system.hunger

    def tick(self):
        """Per-turn update: hunger grows, fear decays slightly."""
        self.hunger = min(1.0, self.hunger + 0.02)
        self.fear_level = max(0.0, self.fear_level - 0.01)
        self.curiosity = max(0.1, min(1.0, self.curiosity))
        self.condition = "Injured" if self.health <= 30 else "Healthy"
        # Sync meters back to memory system
        self.memory_system.hunger = self.hunger
        self.memory_system.fear = self.fear_level
        self.memory_system.curiosity = self.curiosity
        self.memory_system.mood = self.mood

    # ── Memory helpers ─────────────────────────────────────────────────────────

    def get_enhanced_memory_context(self) -> str:
        return self.memory_system.get_contextual_summary()

    def memory_summary(self, limit: int = 5) -> str:
        return self.memory_system.get_summary(limit)

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self, full: bool = False) -> dict:
        d = {
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "health": self.health,
            "motivation": self.motivation,
            "personality": self.personality,
            "memory": self.memory_system.get_summary(8),
            # Extended fields
            "mood": self.mood,
            "condition": self.condition,
            "inventory": list(self.inventory),
            "short_term_goal": self.short_term_goal,
            "long_term_goal": self.long_term_goal,
            "hunger": round(self.hunger, 2),
            "fear": round(self.fear_level, 2),
            "curiosity": round(self.curiosity, 2),
            "is_evil": self.is_evil,
            "is_dead": self.is_dead,
            "relationship_summary": self.memory_system.get_relationship_summary(),
        }
        if full:
            d["full_memory"] = self.memory_system.to_dict()
        return d
