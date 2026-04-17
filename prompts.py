"""prompts.py — Build LLM prompts for NPCs and the storyteller."""

import random
import config


def build_npc_prompt(npc, other_characters: list, world) -> str:
    """Build the full decision prompt for a single NPC."""

    situation = world.global_situation or random.choice([
        "The sun is setting over an unfamiliar landscape.",
        "A low fog rolls in from the east.",
        "A distant bell tolls once and falls silent.",
        "The sky is oddly still — not even wind.",
        "Somewhere in the distance, something moves.",
    ])

    nearby_chars = []
    for c in other_characters:
        if not c.is_dead and npc.can_see(c):
            nearby_chars.append(f"{c.name} ({c.x},{c.y}) [HP:{c.health}]")

    items_nearby = []
    for it in world.items:
        dx, dy = npc.x - it.x, npc.y - it.y
        if dx * dx + dy * dy <= npc.vision_range ** 2:
            items_nearby.append(f"{it.name} ({it.x},{it.y})")

    personality_hint = config.PERSONALITY_HINTS.get(npc.personality, "")
    memory_ctx = npc.get_enhanced_memory_context()
    rel_ctx = npc.memory_system.get_relationship_summary()

    evil_instruction = ""
    if npc.is_evil:
        evil_instruction = (
            "\nYou are secretly THE evil character. You have gathered everyone here to hunt them. "
            "Attack when you have the opportunity. Lie, cheat, steal. "
            "WIN CONDITION: be the last surviving character. "
            "LOSE CONDITION: any character kills you.\n"
        )

    goal_block = ""
    if npc.short_term_goal:
        goal_block += f"  Short-term goal: {npc.short_term_goal}\n"
    if npc.long_term_goal:
        goal_block += f"  Long-term goal: {npc.long_term_goal}\n"

    prompt = f"""Situation: {situation}
Character:
  Name: {npc.name}
  Location: {npc.x},{npc.y}
  Motivation: {npc.motivation}
  Personality: {npc.personality}
  PersonalityHint: {personality_hint}
  Inventory: {', '.join(npc.inventory) or 'Nothing'}
  Health: {npc.health}/{npc.max_health}
  Condition: {npc.condition}
  Mood: {npc.mood}
  Hunger: {'high' if npc.hunger > 0.6 else 'low'}
  Fear: {'high' if npc.fear_level > 0.5 else 'low'}
{goal_block}  Memory & Experience: {memory_ctx}
  Relationships: {rel_ctx or 'No strong feelings about anyone yet'}
Nearby Characters: {', '.join(nearby_chars) if nearby_chars else 'None in sight'}
Nearby Items: {', '.join(items_nearby) if items_nearby else 'None visible'}
{evil_instruction}
Decision Request:
You are {npc.name}. Based on your situation, personality, memory, and the characters/items you can see,
decide what to do this turn.
- If you fear someone, avoid them or prepare to defend yourself.
- If you trust someone, you might seek their help.
- If you are suspicious, investigate or keep distance.
- You can attack any character you can SEE without moving first.
- You can move AND attack in the same turn if you say both.
- You can form alliances by saying "I want to ally with <name>".
- Gossip: share what you know about dangerous characters with others.
- If you are a good character and see evil, feel compelled to stop it (heroism).
- Profanity and extreme behavior are realistic and allowed.
- Set short and long term goals based on your situation.

Respond with EXACTLY two lines:
Dialogue: <one sentence you say aloud, or blank if silent>
Action: <one action from the list below>

Allowed actions:
  move north | move south | move east | move west | move to X,Y
  attack <name>
  use healing potion
  pick up <item>
  drop <item>
  say: <text>
  say to <name>: <text>

Keep your Dialogue and Action to one line each. Be concise."""
    return prompt.strip()
