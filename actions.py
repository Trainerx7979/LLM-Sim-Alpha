"""actions.py — Action execution, attack resolution, and witness handling."""

import re
import math
import random
import config
from world import Item, Speech


# ── Utilities ─────────────────────────────────────────────────────────────────

def sanitize_action(action: str) -> str:
    if not action:
        return ""
    a = action.strip()
    a = re.sub(r'^[\-\—\:\s]+', '', a)
    a = re.sub(r'\s+', ' ', a)
    a = a.rstrip('.,;')
    return a


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def find_target(attacker, target_name: str, characters: list):
    """Find a target by name, or fall back to the nearest visible character."""
    if target_name:
        tl = target_name.lower()
        for c in characters:
            if c is attacker or c.is_dead:
                continue
            if tl in c.name.lower():
                return c

    # Nearest visible character (within attacker's vision range or adjacent)
    candidates = [c for c in characters if c is not attacker and not c.is_dead]
    if not candidates:
        return None
    candidates.sort(key=lambda c: (attacker.x - c.x) ** 2 + (attacker.y - c.y) ** 2)
    nearest = candidates[0]
    dist2 = (attacker.x - nearest.x) ** 2 + (attacker.y - nearest.y) ** 2
    if dist2 <= (attacker.vision_range) ** 2:
        return nearest
    return None


def find_item_in_range(npc, item_name: str, world,
                       max_range: int = config.PICKUP_RANGE):
    name_l = item_name.lower()
    best = None
    best_d2 = max_range ** 2 + 1
    for it in world.items:
        if it.name.lower() != name_l:
            continue
        d2 = (it.x - npc.x) ** 2 + (it.y - npc.y) ** 2
        if d2 <= max_range ** 2 and d2 < best_d2:
            best, best_d2 = it, d2
    return best


# ── Attack resolution ─────────────────────────────────────────────────────────

def _notify_witnesses(world, characters, attacker, target, event_text: str,
                      logger=None):
    """Inform nearby NPCs of an attack event and return witness list."""
    witnesses = []
    fake = Speech(source=attacker, text=event_text, ttl=1)
    for c in characters:
        if c is attacker or c is target or c.is_dead:
            continue
        if c.can_hear(fake):
            witnesses.append(c)
            c.remember(f"witnessed: {event_text}",
                       category="event", priority=4,
                       emotion="fear", related_character=attacker.name)
    return witnesses


def resolve_attack(npc, target_name: str, world, characters: list,
                   logger=None) -> None:
    """Resolve an attack action, update memories, and log the event."""
    target = find_target(npc, target_name, characters)
    if not target:
        msg = f"{npc.name} tried to attack '{target_name or '?'}' — no valid target nearby."
        if logger:
            logger.event(msg)
        return

    hit_chance = config.EVIL_HIT_CHANCE if npc.is_evil else config.GOOD_HIT_CHANCE
    if random.random() <= hit_chance:
        dmg = (random.randint(config.EVIL_DMG_MIN, config.EVIL_DMG_MAX)
               if npc.is_evil
               else random.randint(config.GOOD_DMG_MIN, config.GOOD_DMG_MAX))
        target.health -= dmg
        event_text = f"attack: {npc.name} → {target.name} for {dmg}"
        msg = f"{npc.name} attacks {target.name} for {dmg} damage (HP now {target.health})"
        print(msg)
        if logger:
            logger.event(msg)

        witnesses = _notify_witnesses(world, characters, npc, target, event_text, logger)

        # Attacker and target memories
        npc.remember(f"attacked {target.name} for {dmg}",
                     category="event", priority=3)
        target.remember(f"attacked by {npc.name} for {dmg}",
                        category="event", priority=5,
                        emotion="fear", related_character=npc.name)

        if not witnesses:
            world.add_item(Item("Signs of a struggle here", target.x, target.y, ttl=3))
            if logger:
                logger.event(f"Evidence left at {target.x},{target.y}")
            if npc.is_evil and random.random() < 0.12:
                npc.remember(f"staged scene near {target.name}",
                             category="event", priority=3)

        if target.health <= 0:
            _handle_death(target, npc, witnesses, logger)

    else:
        # Miss
        msg = f"{npc.name} attacks {target.name} but misses."
        if logger:
            logger.event(msg)
        target.remember(f"{npc.name} attacked and missed",
                        category="event", priority=4,
                        emotion="fear", related_character=npc.name)
        _notify_witnesses(world, characters, npc, target,
                          f"attack_miss: {npc.name}→{target.name}", logger)


def _handle_death(target, killer, witnesses: list, logger=None):
    """Mark an NPC as dead and propagate memory updates."""
    target.is_dead = True
    target.health = 0
    msg = f"{target.name} has been killed by {killer.name}."
    print(msg)
    if logger:
        logger.event(msg)
    # Witnesses remember the death
    for w in witnesses:
        w.remember(f"{target.name} was killed by {killer.name}",
                   category="event", priority=5,
                   emotion="fear", related_character=killer.name)
        w.memory_system.grow_suspicion(killer.name, 4)


# ── Main action executor ──────────────────────────────────────────────────────

def execute_action(npc, action: str, world, characters: list,
                   logger=None, rng: random.Random = None) -> None:
    """Execute a parsed action string for the given NPC."""
    if rng is None:
        rng = random

    action = sanitize_action(action)
    if not action:
        return

    al = action.lower()

    # ── MOVE ──────────────────────────────────────────────────────────────────
    if al.startswith("move "):
        rest = action.split(" ", 1)[1].strip()
        if rest.lower().startswith("to"):
            coords = rest.split("to", 1)[1].strip()
            if "," in coords:
                try:
                    xs, ys = coords.split(",", 1)
                    nx = clamp(int(float(xs.strip())), 0, world.size)
                    ny = clamp(int(float(ys.strip())), 0, world.size)
                    npc.x, npc.y = nx, ny
                    msg = f"{npc.name} moves to {npc.x},{npc.y}"
                    if logger:
                        logger.event(msg)
                    # Memory: note movement toward others
                    nearby = [c for c in characters
                               if c is not npc and not c.is_dead
                               and (c.x - npc.x) ** 2 + (c.y - npc.y) ** 2 <= config.HEARING_RANGE ** 2]
                    if nearby:
                        npc.remember(f"moved near {nearby[0].name}",
                                     category="location", priority=2)
                except Exception as e:
                    if logger:
                        logger.event(f"{npc.name} failed to parse move coords: {e}")
        else:
            direction = rest.split()[0].lower() if rest else ""
            if direction in ("north", "n", "up"):
                npc.y = clamp(npc.y - 1, 0, world.size)
            elif direction in ("south", "s", "down"):
                npc.y = clamp(npc.y + 1, 0, world.size)
            elif direction in ("east", "e", "right"):
                npc.x = clamp(npc.x + 1, 0, world.size)
            elif direction in ("west", "w", "left"):
                npc.x = clamp(npc.x - 1, 0, world.size)
            if logger:
                logger.event(f"{npc.name} moves {direction} → {npc.x},{npc.y}")
        return

    # ── ATTACK ────────────────────────────────────────────────────────────────
    if al.startswith("attack"):
        parts = action.split()
        tname = " ".join(parts[1:]).strip() if len(parts) >= 2 else ""
        resolve_attack(npc, tname, world, characters, logger)
        return

    # ── USE HEALING POTION ────────────────────────────────────────────────────
    if "healing potion" in al or al.startswith("use healing potion"):
        idx = next((i for i, it in enumerate(npc.inventory)
                    if "healing potion" in it.lower()), None)
        if idx is not None:
            npc.health = min(npc.max_health, npc.health + 20)
            npc.inventory.pop(idx)
            msg = f"{npc.name} uses a healing potion → HP {npc.health}"
            if logger:
                logger.event(msg)
            npc.remember("used healing potion", category="event", priority=2)
        else:
            if logger:
                logger.event(f"{npc.name} tried to use healing potion but has none")
        return

    # ── PICK UP ───────────────────────────────────────────────────────────────
    if al.startswith(("pick up", "pickup", "take", "use ")):
        parts = action.split()
        if len(parts) >= 3:
            item_name = " ".join(parts[2:]).strip()
            found = find_item_in_range(npc, item_name, world, config.PICKUP_RANGE)
            if found:
                npc.inventory.append(found.name)
                world.items.remove(found)
                msg = f"{npc.name} picked up {found.name}"
                if logger:
                    logger.event(msg)
                priority = (3 if any(w in found.name.lower()
                                     for w in ("sword", "bow", "weapon", "dagger", "knife"))
                            else 2)
                npc.remember(f"picked up {found.name}",
                             category="event", priority=priority)
            else:
                if logger:
                    logger.event(f"{npc.name} tried to pick up '{item_name}' but not found nearby")
        return

    # ── DROP ──────────────────────────────────────────────────────────────────
    if al.startswith("drop "):
        item_name = action.split(" ", 1)[1].strip()
        idx = next((i for i, it in enumerate(npc.inventory)
                    if it.lower() == item_name.lower()), None)
        if idx is not None:
            it = npc.inventory.pop(idx)
            world.add_item(Item(it, npc.x, npc.y, ttl=20))
            if logger:
                logger.event(f"{npc.name} dropped {it} at {npc.x},{npc.y}")
            npc.remember(f"dropped {it} at {npc.x},{npc.y}",
                         category="location", priority=2)
        return

    # ── SAY TO <target>: <text> ───────────────────────────────────────────────
    if al.startswith("say to "):
        try:
            after = action.split("say to ", 1)[1]
            if ":" in after:
                tpart, text = after.split(":", 1)
                tname = tpart.strip()
                text = text.strip()
                target_c = next((c for c in characters
                                 if c.name.lower() == tname.lower()), None)
                if target_c:
                    world.add_speech(Speech(source=npc, text=text,
                                            ttl=config.SPEECH_TTL, target=target_c.name))
                    print(f"{npc.name} → {target_c.name}: {text}")
                    if logger:
                        logger.event(f"{npc.name} says to {target_c.name}: {text}")
                    _process_speech_memory(npc, target_c, text)
                    # Alliance/betrayal detection
                    _detect_alliance_language(npc, target_c, text, characters)
        except Exception as e:
            if logger:
                logger.event(f"{npc.name} failed directed speech: {e}")
        return

    # ── SAY ───────────────────────────────────────────────────────────────────
    if al.startswith("say:") or al.startswith("say "):
        text = (action.split(":", 1)[1].strip() if ":" in action
                else (action.split(" ", 1)[1].strip() if " " in action else ""))
        if text:
            world.add_speech(Speech(source=npc, text=text,
                                    ttl=config.SPEECH_TTL, target=None))
            print(f"{npc.name}: {text}")
            if logger:
                logger.event(f"{npc.name} says: {text}")
            # Update memory of hearers
            for c in characters:
                if c is not npc and not c.is_dead and c.can_hear(world.speeches[-1]):
                    _process_overheard(npc, c, text)
        return

    # ── Unknown ────────────────────────────────────────────────────────────────
    if logger:
        logger.event(f"{npc.name} performs unknown action: {action}")


# ── Speech memory helpers ─────────────────────────────────────────────────────

_HOSTILE_WORDS = re.compile(r'\b(kill|attack|steal|destroy)\b', re.IGNORECASE)
_FRIENDLY_WORDS = re.compile(r'\b(help|promise|trust|ally|together)\b', re.IGNORECASE)
_INTENT_WORDS = re.compile(r'\b(plan|intend|going to|will|want to)\b', re.IGNORECASE)


def _process_speech_memory(speaker, target, text: str):
    if _HOSTILE_WORDS.search(text):
        target.remember(f"heard from {speaker.name}: {text}",
                        category="relationship", priority=3,
                        emotion="fear", related_character=speaker.name)
        target.memory_system.grow_suspicion(speaker.name, 2)
    elif _FRIENDLY_WORDS.search(text):
        target.remember(f"heard from {speaker.name}: {text}",
                        category="relationship", priority=2,
                        emotion="trust", related_character=speaker.name)
    speaker.remember(f"told {target.name}: {text}",
                     category="relationship", priority=2)
    if _INTENT_WORDS.search(text):
        target.memory_system.add_intent(speaker.name, text)


def _process_overheard(speaker, hearer, text: str):
    if _HOSTILE_WORDS.search(text):
        hearer.remember(f"overheard {speaker.name}: {text}",
                        category="relationship", priority=3,
                        emotion="fear", related_character=speaker.name)
    elif _FRIENDLY_WORDS.search(text):
        hearer.remember(f"overheard {speaker.name}: {text}",
                        category="relationship", priority=2,
                        emotion="trust", related_character=speaker.name)


def _detect_alliance_language(speaker, target, text: str, characters: list):
    """Detect alliance formation and betrayal language in speech."""
    tl = text.lower()
    if any(kw in tl for kw in ("alliance", "ally with", "team up", "work together")):
        speaker.memory_system.form_alliance(target.name)
        target.memory_system.form_alliance(speaker.name)
    if any(kw in tl for kw in ("betray", "you lied", "traitor", "never trust")):
        if target.name in speaker.memory_system.alliances:
            speaker.memory_system.betray_alliance(target.name)
