"""storyteller.py — Multi-alignment storyteller for NPC Sim v2"""

import re
import config
from llm import get_llm_response, parse_storyteller_response
from world import Item, Speech
from npc import NPC


# ── Alignment-specific prompt flavours ────────────────────────────────────────

_ALIGNMENT_INSTRUCTIONS = {
    "neutral": (
        "You are neutral. You do not favour good or evil. "
        "Your job is to keep the narrative moving and ensure that "
        "either the evil character wins (last one alive) or the good characters "
        "defeat evil. Place items that create drama. Allow the story to unfold naturally."
    ),
    "benevolent": (
        "You are benevolent. You subtly help the good characters survive and "
        "find the evil one. Place helpful items near struggling characters. "
        "Tip the balance toward good when the evil character gets too powerful."
    ),
    "malevolent": (
        "You are malevolent. You want chaos and death. Favour the evil character "
        "by placing weapons or obstacles near good characters. Enjoy the carnage. "
        "Place ominous items that drive characters to paranoia."
    ),
    "chaotic": (
        "You are chaotic. You make completely unpredictable decisions. "
        "Spawn bizarre items, move characters randomly, whisper strange messages. "
        "You do not care who wins — you crave chaos and surprise."
    ),
    "scientific": (
        "You are a scientific observer. You interfere as little as possible. "
        "Only spawn items or send messages when the simulation has clearly stalled "
        "(same character repeating actions for 3+ turns). Log your observations neutrally."
    ),
}

_ALLOWED_EVENTS = (
    "EVENT: spawn_item <name> at X,Y\n"
    "EVENT: ambient move <CharacterName> to X,Y\n"
    "EVENT: ambient message <text> near X,Y"
)


def ask_storyteller_initial(world, characters, alignment: str = "neutral") -> list[str]:
    """Generate the opening situation and initial world events."""
    alignment = alignment if alignment in _ALIGNMENT_INSTRUCTIONS else "neutral"
    instr = _ALIGNMENT_INSTRUCTIONS[alignment]
    summary = world.summary_text(characters)

    prompt = f"""You are the storyteller for a small simulation.
Alignment: {alignment.upper()}
{instr}

World summary:
{summary}

One character is secretly evil but the others don't know it. Characters don't know how
they arrived here, who anyone else is, or how to leave.

Write a short evocative situation (one sentence) that sets the tone, then optionally
suggest up to 2 world events to happen this turn.

Format:
SITUATION: <one evocative sentence>
{_ALLOWED_EVENTS}

Keep it brief and atmospheric. No more than 2 events."""

    raw = get_llm_response(prompt)
    if not raw:
        return []

    situation, events = parse_storyteller_response(raw)
    if situation:
        world.global_situation = situation
        print(f"[Storyteller] Situation: {situation}")

    return events


def ask_storyteller(world, characters, alignment: str = "neutral",
                    recent_speeches=None) -> list[str]:
    """Generate up to 2 world events for the current turn."""
    alignment = alignment if alignment in _ALIGNMENT_INSTRUCTIONS else "neutral"
    instr = _ALIGNMENT_INSTRUCTIONS[alignment]
    summary = world.summary_text(characters)

    speech_lines = ""
    if recent_speeches:
        speech_lines = "\nRecent dialogue:\n" + "\n".join(
            f"  {s.source.name}: {s.text[:80]}" for s in recent_speeches[-6:]
        )

    prompt = f"""You are the storyteller (alignment: {alignment.upper()}).
{instr}

World state (turn {world.turn}):
{summary}{speech_lines}

Remember: one character may be evil. Ensure the story progresses toward a conclusion.
If characters seem stuck, place something that provokes action.

Suggest up to 2 world events. Output each as a single line:
{_ALLOWED_EVENTS}

No preamble. At most 2 events."""

    raw = get_llm_response(prompt)
    if not raw:
        return []

    _, events = parse_storyteller_response(raw)
    return events


def storyteller_authorize(npc, action: str, alignment: str = "neutral") -> str:
    """Ask the storyteller whether to ALLOW or MODIFY an NPC's proposed action.

    Returns the (possibly modified) action string.
    """
    prompt = f"""Storyteller role (alignment: {alignment.upper()}):
Keep the narrative logical and progressing.
Note: the evil character is highly skilled and should nearly always deal damage when attacking.
Otherwise stay neutral and make decisions that will progress the story.

Character: {npc.name}
Proposed action: {action}
Recent memory: {npc.memory_system.get_summary(5)}

Respond with EXACTLY one of:
ALLOW
MODIFY: <new_action>"""

    try:
        text = get_llm_response(prompt, timeout=10)
        if text and "MODIFY:" in text:
            modified = text.split("MODIFY:", 1)[1].strip().splitlines()[0].strip()
            if modified:
                return modified
    except Exception:
        pass
    return action


def handle_story_events(events: list[str], world, characters,
                        logger=None) -> list[str]:
    """Apply storyteller events to the world.  Returns log lines."""
    log = []
    for ev in events:
        ev = ev.strip()
        if not ev:
            continue

        # ── spawn_item ─────────────────────────────────────────────────────────
        if ev.lower().startswith("spawn_item"):
            m = re.match(r'spawn_item\s+(.+?)\s+at\s+(\d+)[,\s]+(\d+)', ev, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                x, y = int(m.group(2)), int(m.group(3))
                world.add_item(Item(name, x, y, ttl=30))
                msg = f"[Storyteller] Spawned '{name}' at {x},{y}"
                log.append(msg)
                print(msg)
                if logger:
                    logger.event(msg)
            continue

        # ── ambient move ───────────────────────────────────────────────────────
        if ev.lower().startswith("ambient move"):
            m = re.match(r'ambient move\s+(.+?)\s+to\s+(\d+)[,\s]+(\d+)', ev, re.IGNORECASE)
            if m:
                char_name = m.group(1).strip()
                x = min(int(m.group(2)), world.size)
                y = min(int(m.group(3)), world.size)
                target = next(
                    (c for c in characters if c.name.lower() == char_name.lower()),
                    None,
                )
                if target:
                    target.x, target.y = x, y
                    msg = f"[Storyteller] Moved {target.name} to {x},{y}"
                    log.append(msg)
                    print(msg)
                    if logger:
                        logger.event(msg)
            continue

        # ── ambient message ────────────────────────────────────────────────────
        if ev.lower().startswith("ambient message"):
            m = re.match(r'ambient message\s+(.+?)\s+near\s+(\d+)[,\s]+(\d+)', ev, re.IGNORECASE)
            if m:
                text = m.group(1).strip()
                x, y = int(m.group(2)), int(m.group(3))

                class _Ghost:
                    name = "Storyteller"

                ghost = _Ghost()
                ghost.x = x
                ghost.y = y
                world.add_speech(Speech(source=ghost, text=text, ttl=3))
                msg = f"[Storyteller] Ambient message near {x},{y}: {text}"
                log.append(msg)
                print(msg)
                if logger:
                    logger.event(msg)
            continue

        msg = f"[Storyteller] Unknown event: {ev}"
        log.append(msg)
        if logger:
            logger.event(msg)

    return log
