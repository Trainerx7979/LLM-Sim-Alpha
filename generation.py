"""generation.py — Character and world generation for NPC Sim v2"""

import random
import config
from npc import NPC
from world import World, Item


def generate_characters(count: int = config.DEFAULT_CHARACTER_COUNT,
                         rng: random.Random = None,
                         world_size: int = config.DEFAULT_WORLD_SIZE) -> list[NPC]:
    """Generate `count` characters with exactly one evil NPC."""
    if rng is None:
        rng = random

    names = rng.sample(config.NAME_POOL, min(count, len(config.NAME_POOL)))
    # Pad with numbered names if needed
    while len(names) < count:
        names.append(f"Traveler {len(names)+1}")

    evil_index = rng.randint(0, count - 1)
    characters = []
    for i, name in enumerate(names):
        is_evil = (i == evil_index)
        motivation = rng.choice(config.MOTIVATIONS)
        personality = "Ruthless" if is_evil else rng.choice(config.PERSONALITIES)
        inventory = list(rng.choice(config.INVENTORY_CHOICES))
        npc = NPC(
            name=name,
            x=rng.randint(5, world_size - 5),
            y=rng.randint(5, world_size - 5),
            motivation=motivation,
            personality=personality,
            health=100,
            inventory=inventory,
            is_evil=is_evil,
        )
        characters.append(npc)

    return characters


def generate_world(size: int = config.DEFAULT_WORLD_SIZE) -> World:
    return World(size=size)


def populate_initial_items(world: World, characters: list,
                            rng: random.Random = None):
    """Add a few starting items near characters."""
    if rng is None:
        rng = random
    starter_items = [
        ("Shiny Coin", 30),
        ("Torn Map Fragment", 30),
        ("Empty Canteen", 30),
        ("Healing Potion", 30),
    ]
    for name, ttl in starter_items[:max(1, len(characters) // 2)]:
        ref = rng.choice(characters)
        x = max(0, min(world.size, ref.x + rng.randint(-4, 4)))
        y = max(0, min(world.size, ref.y + rng.randint(-4, 4)))
        world.add_item(Item(name, x, y, ttl=ttl))
