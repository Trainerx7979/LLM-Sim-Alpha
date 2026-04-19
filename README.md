# NPC Simulation Alpha

A research-oriented emergent-behaviour simulation in which autonomous NPCs,
driven by a local LLM (Ollama), navigate a 2D world while one secretly-evil
character tries to eliminate everyone else.

The LOG file is stored for each simulation, and a Visual Log replayer is
included. You can review log files visually, and have access to ALL the
data for each character at their turn. It's also stored in a human-readable
format so that you can just browse or search for the section in question.

How is this different from LlmSandbox? Well for a start, the storyteller
in this can be neutral (default) or it can be other things. Dropdown box
selects. Every detail is recorded in the logs. There is also a viewer app
provided with which you can load and replay log files.
Regardless of the number of characters in a sim, one of them will be evil.
The evil one will try to take the others out. I've seen the evil one do
some impressive things. On Qwen2.5:7b one round he actually realized that
the storyteller existed, and made a plea to a 'higher power' that appealed
to what he thought the storyteller's goal was. This allowed him to use the
storyteller to manipulate the world to hide evidence of his crimes.
If you see anything interesting like that, save the logs!

---

## Requirements

| Package  | Purpose                            |
|----------|------------------------------------|
| Python 3.11+ | Type hints, threading           |
| pygame ≥ 2.5 | Game window, rendering          |
| requests | Ollama API calls                   |
| Pillow   | Animated GIF sprite support        |
| tkinter  | Control panel (stdlib on most OSes)|
| Ollama   | Local LLM inference server         |

Install Python dependencies:
```bash
pip install pygame requests Pillow
```

Install & run Ollama: https://ollama.com/download  
Pull a model (default is `llama3.1`):
```bash
ollama pull llama3.1
```

---

## Quick Start

```bash
python main.py
```

This opens the **TkInter control panel**.  Hit **Start** to launch the
simulation.  A separate Pygame window will open showing the world.

### Command-line options

```
python main.py                           # Full GUI
python main.py --seed 42                 # Pre-set seed
python main.py --count 8 --alignment malevolent
python main.py --play sim_log.jsonl      # Playback viewer only
python main.py --headless --seed 42      # No GUI, logs to stdout/file
```

---

## Project Structure

```
npc_sim_v2/
├── main.py           Entry point / CLI
├── app.py            TkInter control panel
├── renderer.py       Pygame rendering layer
├── simulation.py     Simulation loop (background thread)
├── config.py         All constants and defaults
├── npc.py            NPC class
├── memory.py         Enhanced memory system
├── world.py          World / Item / Speech classes
├── actions.py        Action executor & attack resolution
├── prompts.py        LLM prompt builder
├── generation.py     Character & world generation
├── storyteller.py    Multi-alignment storyteller agent
├── llm.py            Ollama API wrapper
├── logger.py         JSONL logger
├── playback.py       Log replay viewer
├── particles.py      Particle emitter, damage numbers, sprites
├── images/           Sprite directory (optional)
└── requirements.txt
```

---

## Configuration

All constants live in **`config.py`** and can also be changed live in the
**Configuration** tab of the control panel.

Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `OLLAMA_MODEL` | `llama3.1` | LLM model name |
| `DEFAULT_CHARACTER_COUNT` | 6 | Number of NPCs |
| `DEFAULT_ALIGNMENT` | `neutral` | Storyteller alignment |
| `STORY_INTERVAL` | 3 | Turns between storyteller events |
| `EVIL_VISION_RANGE` | 40 | Evil NPC vision (tiles) |
| `HEARING_RANGE` | 20 | Normal NPC hearing range (tiles) |

---

## Storyteller Alignments

| Alignment  | Behaviour |
|------------|-----------|
| `neutral`  | Lets the story unfold naturally; keeps things moving |
| `benevolent` | Subtly helps good characters; places healing items |
| `malevolent` | Helps evil; places weapons near victims, drives paranoia |
| `chaotic`  | Completely unpredictable; spawns bizarre items |
| `scientific` | Minimal interference; only intervenes when sim stalls |

---

## Sprites (Optional)

Place images in the `images/` directory:

| Filename | Used for |
|----------|----------|
| `npc_default.png` | Default NPC sprite (any size, scaled to tile) |
| `npc_dead.png` | Dead NPC sprite |
| `<name>.png` | NPC-specific sprite (e.g. `asha.png`) |
| `<name>.gif` | Animated NPC (walk cycle, etc.) |
| `campfire.gif` | Ambient looping animation (place via storyteller) |
| `<item_name>.png` | Item sprite (e.g. `healing_potion.png`) |

If a sprite is not found, a coloured circle is drawn instead.

---

## Logging

Each run appends to `sim_log.jsonl` (configurable).  Format:

```jsonl
{"_type":"header","seed":12345,"storyteller_alignment":"neutral","world_size":40,...}
{"_type":"turn","turn":1,"events":[...],"characters":[...],"speeches":[...],"items":[...]}
...
```

Each character entry includes **all** standard fields **plus** extended fields:
`mood`, `inventory`, `short_term_goal`, `long_term_goal`, `hunger`, `fear`,
`relationships`, and `full_memory` (with suspicions, alliances, monologue, etc.)

---

## Playback

Open any `.jsonl` log in the playback viewer:

```bash
python main.py --play sim_log.jsonl
# or from within the control panel: Log file → Open Playback
```

Controls:
- `⏮ ◀◀ ◀ ▶ ▶▶ ⏭` — step through turns
- **Play** — auto-advance at configurable speed
- **Scrubber** — jump to any turn
- **Click an NPC** — inspect their full brain state at that turn

---

## NPC Behaviour

Each NPC has:
- **Personality** (Cautious / Brave / Greedy / Loyal / Suspicious / Curious / Ruthless)
- **Mood** (calm / anxious / angry / afraid / hopeful / confused / determined / suspicious)
- **Memory** (categorised: observation, event, relationship, gossip, intent, suspicion, monologue)
- **Relationship tracking** (trust / fear / suspicion per character)
- **Suspicion meter** (0–10 per character, triggers memories)
- **Alliances** (formed via speech; can be betrayed)
- **Internal monologue** (stored but never spoken)
- **Meters**: hunger, fear, curiosity
- **Short & long-term goals** (derived from memory)
- **Gossip** (NPCs share what they've heard)

### Actions available to NPCs

```
move north/south/east/west
move to X,Y
attack <character>
use healing potion
pick up <item>
drop <item>
say: <text>
say to <character>: <text>
```

---

## Architecture Notes

- **TkInter** runs in the main thread (required on macOS/Windows).
- **Pygame** renderer runs in a daemon thread, reading `SimState` safely.
- **Simulation** loop runs in a daemon thread; writes to `SimState` under a lock.
- LLM calls are **synchronous** within the sim thread (Ollama is local, fast enough).
- All random decisions use a **seeded `random.Random` instance** for determinism.

---

## Emergent Behaviours to Watch For

- NPCs warning each other about the evil character after witnessing an attack
- Alliance formation and betrayal
- Evil NPC eliminating isolated targets before suspicion rises
- Good NPCs forming ad-hoc "police" groups
- Paranoia spirals from overhearing ambiguous speech
- Storyteller steering a stalled simulation back to life

---

## Research Notes

Every turn is fully logged with:
- Random seed (for deterministic replay)
- NPC brain states (memory, mood, suspicions, alliances, monologue)
- Storyteller alignment and actions
- Attack outcomes and witness lists
- Speech content and overheard reactions

This makes the simulation suitable for studying emergent social behaviour in
LLM-based agents.
