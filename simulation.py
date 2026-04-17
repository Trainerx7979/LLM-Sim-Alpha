"""simulation.py — Core simulation loop running in a background thread."""

import threading
import time
import random
import re
import config
from generation import generate_characters, generate_world, populate_initial_items
from world import Speech
from llm import get_llm_response, parse_npc_response
from prompts import build_npc_prompt
from actions import execute_action
from storyteller import (
    ask_storyteller_initial, ask_storyteller,
    storyteller_authorize, handle_story_events,
)
from logger import SimLogger


# ── Shared state ──────────────────────────────────────────────────────────────

class SimState:
    """Thread-safe container for simulation state shared with the renderer."""

    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.paused = False
        self.turn = 0
        self.characters = []
        self.dead_characters = []     # kept for rendering tombstones
        self.world = None
        self.log_lines: list[str] = []
        self.selected_npc = None
        self.victory = ""             # "" | "evil" | "good"
        self.speed_delay = 0.0        # extra seconds between turns
        self.pending_attack_events: list[dict] = []   # for particle spawning
        self.storyteller_alignment = config.DEFAULT_ALIGNMENT

    def snapshot(self):
        """Return a shallow copy of render-relevant state, thread-safely."""
        with self._lock:
            return {
                "turn": self.turn,
                "characters": list(self.characters),
                "dead_characters": list(self.dead_characters),
                "world": self.world,
                "selected_npc": self.selected_npc,
                "victory": self.victory,
                "log_lines": list(self.log_lines[-80:]),
                "pending_attack_events": list(self.pending_attack_events),
            }

    def clear_attack_events(self):
        with self._lock:
            self.pending_attack_events.clear()

    def add_log(self, text: str):
        with self._lock:
            self.log_lines.append(text)
            if len(self.log_lines) > 500:
                self.log_lines = self.log_lines[-400:]


# ── Simulation thread ─────────────────────────────────────────────────────────

class Simulation:
    """Runs the simulation loop in a daemon thread."""

    def __init__(self, state: SimState):
        self.state = state
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.logger: SimLogger | None = None
        self._rng: random.Random = random.Random()
        self._seed: int | None = None

    # ── Control ───────────────────────────────────────────────────────────────

    def start(self, seed: int | None = None,
              count: int = config.DEFAULT_CHARACTER_COUNT,
              alignment: str = config.DEFAULT_ALIGNMENT,
              world_size: int = config.DEFAULT_WORLD_SIZE,
              log_file: str = config.LOG_FILE):
        """Configure and launch the simulation thread."""
        self._stop_event.clear()
        self._seed = seed if seed is not None else random.randint(0, 2 ** 31)
        self._rng = random.Random(self._seed)

        # Build world and characters
        world = generate_world(size=world_size)
        chars = generate_characters(count=count, rng=self._rng, world_size=world_size)
        populate_initial_items(world, chars, rng=self._rng)

        # Logger
        self.logger = SimLogger(
            filename=log_file,
            seed=self._seed,
            alignment=alignment,
            world_size=world_size,
        )

        with self.state._lock:
            self.state.characters = chars
            self.state.dead_characters = []
            self.state.world = world
            self.state.turn = 0
            self.state.victory = ""
            self.state.log_lines = []
            self.state.running = True
            self.state.paused = False
            self.state.storyteller_alignment = alignment

        self.logger.write_header(chars)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.state.running = False

    def pause(self):
        self.state.paused = True

    def resume(self):
        self.state.paused = False

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run(self):
        state = self.state
        log = self.logger
        alignment = state.storyteller_alignment

        # Initial storyteller
        events = ask_storyteller_initial(state.world, state.characters, alignment)
        handle_story_events(events, state.world, state.characters, log)

        turn = 0
        while not self._stop_event.is_set():
            # Pause
            while state.paused and not self._stop_event.is_set():
                time.sleep(0.1)
            if self._stop_event.is_set():
                break

            # Check victory
            alive = [c for c in state.characters if not c.is_dead]
            if len(alive) <= 1:
                if alive:
                    winner = alive[0]
                    state.victory = "evil" if winner.is_evil else "good"
                    state.add_log(f"=== {'EVIL' if winner.is_evil else 'GOOD'} WINS — {winner.name} is the last survivor ===")
                    if log:
                        log.event(f"Victory: {state.victory} — {winner.name}")
                        log.finalize(alive, [], state.world.items)
                break

            turn += 1
            with state._lock:
                state.turn = turn
            log.start_turn(turn)

            # Update memory turn counters
            for c in state.characters:
                if not c.is_dead:
                    c.memory_system.current_turn = turn
                    c.tick()

            # Storyteller every N turns
            if turn % config.STORY_INTERVAL == 0:
                events = ask_storyteller(
                    state.world, [c for c in state.characters if not c.is_dead],
                    alignment, recent_speeches=state.world.speeches,
                )
                handle_story_events(events, state.world, state.characters, log)

            # Each NPC takes a turn
            for character in list(state.characters):
                if character.is_dead or self._stop_event.is_set():
                    continue
                other = [c for c in state.characters if c is not character and not c.is_dead]
                prompt = build_npc_prompt(character, other, state.world)

                # Storyteller authorisation (only for attacks, to avoid slowdown)
                raw = get_llm_response(prompt)
                dialogue, action = parse_npc_response(raw)

                # Optionally authorise the action
                if action and any(kw in action.lower() for kw in ("attack", "kill")):
                    action = storyteller_authorize(character, action, alignment)

                character.last_dialogue = dialogue
                character.last_action = action

                if dialogue:
                    d = dialogue
                    if "Action:" in d:
                        d = d.split("Action:")[0].strip()
                    state.world.add_speech(Speech(source=character, text=d,
                                                  ttl=config.SPEECH_TTL))
                    # Memory: remember significant statements
                    if re.search(r'\b(kill|attack|help|promise|trust|afraid|ally)\b', d, re.IGNORECASE):
                        priority = 3 if re.search(r'\b(kill|attack)\b', d, re.IGNORECASE) else 2
                        character.remember(f"said: {d}", category="relationship", priority=priority)
                    # Internal monologue: generate a private thought occasionally
                    if self._rng.random() < 0.3:
                        character.memory_system.add_monologue(f"I wonder: {d[:60]}")

                    log.event(f"{character.name}: {d}")
                    state.add_log(f"[T{turn}] {character.name}: {d}")

                execute_action(character, action, state.world,
                               [c for c in state.characters if not c.is_dead],
                               logger=log, rng=self._rng)

                log.event(f"Action: {action}")
                state.add_log(f"[T{turn}] {character.name} → {action}")

                # Update goals from memory
                self._update_goals(character)

            # Remove dead NPCs from active list, keep for renderer
            newly_dead = [c for c in state.characters if c.is_dead
                          and c not in state.dead_characters]
            for c in newly_dead:
                state.dead_characters.append(c)
                state.add_log(f"[T{turn}] {c.name} has died.")
                for other in state.characters:
                    if other is not c and not other.is_dead:
                        other.remember(f"{c.name} has died",
                                       category="event", priority=5, emotion="fear")
            state.characters = [c for c in state.characters if not c.is_dead]

            # Tick world
            state.world.tick()

            # Log turn
            log.finalize(
                state.characters + state.dead_characters,
                state.world.speeches,
                state.world.items,
            )

            # Speed delay
            time.sleep(max(0.0, state.speed_delay))

        state.running = False
        if log:
            log.event("Simulation ended.")
        print("[Simulation] Thread exited.")

    def _update_goals(self, npc):
        """Derive short-term goal from recent memories."""
        recent = [m.text for m in npc.memory_system.memories[-3:]]
        if not recent:
            return
        # Simple heuristic: if recent memory mentions an attack, set a defensive goal
        combined = " ".join(recent).lower()
        if "attack" in combined or "kill" in combined:
            npc.short_term_goal = "Avoid danger and stay alive"
        elif "healing potion" in combined:
            npc.short_term_goal = "Find healing"
        elif "suspicious" in combined:
            npc.short_term_goal = "Investigate suspicious character"
        elif not npc.short_term_goal:
            npc.short_term_goal = "Explore and assess situation"
