"""memory.py — Enhanced memory system for NPC Sim v2"""

from collections import defaultdict


class Memory:
    """A single memory entry with metadata."""
    __slots__ = ("text", "category", "priority", "emotion",
                 "related_character", "turn_created", "decay")

    CATEGORIES = frozenset([
        "observation", "relationship", "event", "location",
        "emotion", "suspicion", "gossip", "intent", "monologue",
    ])

    def __init__(self, text, category="observation", priority=1,
                 emotion=None, related_character=None):
        self.text = text
        self.category = category
        self.priority = priority          # 1‑5, higher = more important
        self.emotion = emotion            # fear | anger | trust | gratitude | suspicion
        self.related_character = related_character
        self.turn_created = 0
        self.decay = 0

    def __repr__(self):
        return f"[{self.category}|p{self.priority}] {self.text}"

    def to_dict(self):
        return {
            "text": self.text,
            "category": self.category,
            "priority": self.priority,
            "emotion": self.emotion,
            "related": self.related_character,
            "turn": self.turn_created,
        }


class EnhancedMemorySystem:
    """Categorised, prioritised memory with relationships, suspicions,
    alliances, gossip, intent, and internal monologue."""

    MAX_MEMORIES = 60
    PRUNE_TO = 45

    def __init__(self):
        self.memories: list[Memory] = []
        self.relationships: dict = defaultdict(
            lambda: {"trust": 0, "fear": 0, "suspicion": 0, "interactions": 0}
        )
        self.important_locations: dict = {}
        self.current_turn: int = 0

        # Extended fields
        self.internal_monologue: list[Memory] = []   # private thoughts, never spoken
        self.suspicions: dict[str, int] = {}         # name → 0‑10
        self.alliances: dict[str, bool] = {}         # name → True
        self.known_liars: set[str] = set()
        self.short_term_goals: list[str] = []
        self.long_term_goals: list[str] = []
        self.mood: str = "calm"                      # from config.MOODS
        self.hunger: float = 0.0                     # 0‑1
        self.fear: float = 0.0                       # 0‑1
        self.curiosity: float = 0.5                  # 0‑1

    # ── Public API ──────────────────────────────────────────────────────────────

    def add_memory(self, text, category="observation", priority=1,
                   emotion=None, related_character=None):
        if not text:
            return
        mem = Memory(text, category, priority, emotion, related_character)
        mem.turn_created = self.current_turn

        if category == "monologue":
            self.internal_monologue.append(mem)
            if len(self.internal_monologue) > 20:
                self.internal_monologue = self.internal_monologue[-15:]
            return

        self.memories.append(mem)

        # Update relationship and suspicion tables
        if related_character and category in ("relationship", "suspicion", "event", "gossip", "intent"):
            rel = self.relationships[related_character]
            if emotion == "fear":
                rel["fear"] += 1
                self._raise_suspicion(related_character, 1)
            elif emotion in ("anger", "suspicion"):
                rel["suspicion"] += 1
                self._raise_suspicion(related_character, 2)
            elif emotion == "trust":
                rel["trust"] += 1
            rel["interactions"] += 1

        # Drive mood updates
        self._update_mood(emotion)
        # Drive meter updates
        if emotion == "fear":
            self.fear = min(1.0, self.fear + 0.15)
        elif emotion == "trust":
            self.fear = max(0.0, self.fear - 0.05)

        self._prune_memories()

    def add_gossip(self, source_name: str, about_name: str, gossip_text: str):
        self.add_memory(
            f"Heard from {source_name} about {about_name}: {gossip_text}",
            category="gossip", priority=3, related_character=about_name,
        )

    def add_intent(self, character_name: str, intent_text: str):
        self.add_memory(
            f"{character_name} said they plan to: {intent_text}",
            category="intent", priority=3, related_character=character_name,
        )

    def add_monologue(self, text: str):
        self.add_memory(text, category="monologue", priority=2)

    def form_alliance(self, character_name: str):
        self.alliances[character_name] = True
        self.relationships[character_name]["trust"] += 3
        self.add_memory(
            f"Formed alliance with {character_name}",
            category="relationship", priority=4, emotion="trust",
            related_character=character_name,
        )

    def betray_alliance(self, character_name: str):
        self.alliances.pop(character_name, None)
        self.known_liars.add(character_name)
        self.relationships[character_name]["suspicion"] += 5
        self._raise_suspicion(character_name, 5)
        self.add_memory(
            f"{character_name} BETRAYED our alliance!",
            category="event", priority=5, emotion="anger",
            related_character=character_name,
        )

    def grow_suspicion(self, character_name: str, amount: int = 1):
        self._raise_suspicion(character_name, amount)

    def set_short_term_goal(self, goal: str):
        self.short_term_goals = [goal] + self.short_term_goals[:2]

    def set_long_term_goal(self, goal: str):
        self.long_term_goals = [goal] + self.long_term_goals[:2]

    # ── Summaries ──────────────────────────────────────────────────────────────

    def get_summary(self, limit: int = 10) -> str:
        visible = [m for m in self.memories if m.category != "monologue"]
        if not visible:
            return "No strong memories."
        sorted_mems = sorted(
            visible,
            key=lambda m: (m.priority, -(self.current_turn - m.turn_created)),
            reverse=True,
        )
        return "; ".join(m.text for m in sorted_mems[:limit])

    def get_monologue_summary(self, limit: int = 5) -> str:
        if not self.internal_monologue:
            return ""
        return "; ".join(m.text for m in self.internal_monologue[-limit:])

    def get_relationship_summary(self) -> str:
        parts = []
        for char, rel in self.relationships.items():
            if rel["fear"] > 2:
                parts.append(f"AFRAID of {char}")
            elif rel["suspicion"] > 2:
                parts.append(f"SUSPICIOUS of {char}")
            elif rel["trust"] > 2:
                parts.append(f"TRUSTS {char}")
            if char in self.alliances:
                parts.append(f"ALLIED with {char}")
            if char in self.known_liars:
                parts.append(f"KNOWS {char} lied")
        sus_high = [(k, v) for k, v in self.suspicions.items() if v >= 4]
        for name, level in sorted(sus_high, key=lambda x: -x[1])[:2]:
            if not any(name in p for p in parts):
                parts.append(f"VERY SUSPICIOUS of {name} (level {level})")
        return "; ".join(parts) if parts else ""

    def get_contextual_summary(self) -> str:
        parts = []
        recent = [m for m in self.memories
                  if self.current_turn - m.turn_created < 3
                  and m.category != "monologue"]
        if recent:
            parts.append("Recent: " + "; ".join(m.text for m in recent[:3]))
        important = [m for m in self.memories if m.priority >= 4 and m.category != "monologue"]
        if important:
            parts.append("Important: " + "; ".join(m.text for m in important[:2]))
        rel = self.get_relationship_summary()
        if rel:
            parts.append(rel)
        threats = [m for m in self.memories
                   if m.category in ("suspicion", "event") and m.emotion in ("fear", "anger")]
        if threats:
            parts.append("Threats: " + "; ".join(m.text for m in threats[:2]))
        return " | ".join(parts) if parts else "No strong memories."

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "memories": [m.to_dict() for m in self.memories],
            "relationships": {k: dict(v) for k, v in self.relationships.items()},
            "suspicions": dict(self.suspicions),
            "alliances": list(self.alliances.keys()),
            "known_liars": list(self.known_liars),
            "monologue": [m.text for m in self.internal_monologue[-5:]],
            "short_term_goals": self.short_term_goals,
            "long_term_goals": self.long_term_goals,
            "mood": self.mood,
            "hunger": round(self.hunger, 2),
            "fear": round(self.fear, 2),
            "curiosity": round(self.curiosity, 2),
        }

    # ── Internals ──────────────────────────────────────────────────────────────

    def _raise_suspicion(self, name: str, amount: int):
        self.suspicions[name] = min(10, self.suspicions.get(name, 0) + amount)
        if self.suspicions[name] >= 6 and name not in self.known_liars:
            # Generate a high-priority suspicion memory if not already at max
            existing = [m for m in self.memories
                        if m.category == "suspicion" and m.related_character == name
                        and self.current_turn - m.turn_created < 5]
            if not existing:
                self.add_memory(
                    f"I'm becoming very suspicious of {name}",
                    category="suspicion", priority=4, emotion="suspicion",
                    related_character=name,
                )

    def _update_mood(self, emotion):
        if emotion == "fear":
            self.mood = "afraid"
            self.fear = min(1.0, self.fear + 0.1)
        elif emotion == "anger":
            self.mood = "angry"
        elif emotion == "trust":
            if self.mood not in ("angry", "afraid"):
                self.mood = "calm"
        elif emotion == "suspicion":
            self.mood = "suspicious"

    def _prune_memories(self):
        if len(self.memories) > self.MAX_MEMORIES:
            sorted_mems = sorted(
                self.memories,
                key=lambda m: (m.priority, -(self.current_turn - m.turn_created)),
                reverse=True,
            )
            self.memories = sorted_mems[:self.PRUNE_TO]
