"""world.py — World, Item, and Speech for NPC Sim v2"""

import config


class Speech:
    """A spoken (or broadcast) message with a TTL."""

    def __init__(self, source, text: str, ttl: int = config.SPEECH_TTL, target=None):
        self.source = source          # NPC object (or a stub with .x/.y)
        self.text: str = text
        self.ttl: int = ttl
        self.target: str | None = target   # name of target NPC, or None for broadcast

    def tick(self) -> bool:
        self.ttl -= 1
        return self.ttl > 0

    def to_dict(self) -> dict:
        return {
            "speaker": self.source.name,
            "text": self.text,
            "x": self.source.x,
            "y": self.source.y,
            "target": self.target,
        }


class Item:
    """A world object that can be picked up or observed."""

    def __init__(self, name: str, x: int, y: int,
                 ttl: int | None = config.ITEM_TTL_DEFAULT,
                 description: str = ""):
        self.name: str = name
        self.x: int = x
        self.y: int = y
        self.ttl: int | None = ttl
        self.description: str = description or name
        self.sprite_name: str = name.lower().replace(" ", "_")

    def tick(self) -> bool:
        if self.ttl is None:
            return True
        self.ttl -= 1
        return self.ttl > 0

    def to_dict(self) -> dict:
        return {"name": self.name, "x": self.x, "y": self.y,
                "ttl": self.ttl, "description": self.description}


class World:
    """Holds the shared world state: items, speeches, global situation."""

    def __init__(self, size: int = config.DEFAULT_WORLD_SIZE):
        self.size: int = size
        self.speeches: list[Speech] = []
        self.items: list[Item] = []
        self.global_situation: str = ""
        self.turn: int = 0

    def add_speech(self, speech: Speech):
        self.speeches.append(speech)

    def add_item(self, item: Item):
        self.items.append(item)

    def tick(self):
        """Advance TTLs for all speeches and items, removing expired ones."""
        self.speeches = [s for s in self.speeches if s.tick()]
        self.items = [i for i in self.items if i.tick()]
        self.turn += 1

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "global_situation": self.global_situation,
            "items": [i.to_dict() for i in self.items],
            "speeches": [s.to_dict() for s in self.speeches],
        }

    def summary_text(self, characters) -> str:
        """Compact text summary for storyteller prompts."""
        char_parts = [f"{c.name}@{c.x},{c.y} HP:{c.health}" for c in characters]
        item_parts = [f"{i.name}@{i.x},{i.y}" for i in self.items]
        speech_parts = [f"{s.source.name}: {s.text[:40]}" for s in self.speeches]
        return (
            f"Characters: {'; '.join(char_parts)}\n"
            f"Items: {', '.join(item_parts) or 'None'}\n"
            f"Recent speech: {'; '.join(speech_parts) or 'None'}"
        )
