"""config.py — All simulation constants and defaults for NPC Sim v2"""

# ── Screen & World ─────────────────────────────────────────────────────────────
SCREEN_W = 900
SCREEN_H = 750
WORLD_SIZE = 40
BASE_SCALE = SCREEN_W // (WORLD_SIZE + 2)   # pixels per tile at zoom 1.0
DEFAULT_ZOOM = 1.0
MIN_ZOOM = 0.4
MAX_ZOOM = 3.0
FPS = 60

# ── Simulation defaults ────────────────────────────────────────────────────────
DEFAULT_CHARACTER_COUNT = 6
DEFAULT_SEED = None          # None = random each run
HEARING_RANGE = 20
SPEECH_TTL = 6
ITEM_TTL_DEFAULT = 30
PICKUP_RANGE = 5
STORY_INTERVAL = 3           # storyteller fires every N turns
DEFAULT_WORLD_SIZE = 40

# ── Evil tuning ────────────────────────────────────────────────────────────────
EVIL_VISION_RANGE = 40
EVIL_ADVANTAGE = True
EVIL_HIT_CHANCE = 0.80
GOOD_HIT_CHANCE = 0.75
EVIL_DMG_MIN, EVIL_DMG_MAX = 36, 67
GOOD_DMG_MIN, GOOD_DMG_MAX = 6, 20

# ── LLM ───────────────────────────────────────────────────────────────────────
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1"
LLM_TIMEOUT = 30

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE = "sim_log.jsonl"

# ── Storyteller alignments ─────────────────────────────────────────────────────
STORYTELLER_ALIGNMENTS = ["neutral", "benevolent", "malevolent", "chaotic", "scientific"]
DEFAULT_ALIGNMENT = "neutral"

# ── Name pool ─────────────────────────────────────────────────────────────────
NAME_POOL = [
    "Asha", "Borin", "Celia", "Darek", "Elin", "Fenn", "Gara", "Hale", "Iris", "Jor",
    "Kira", "Ludo", "Mira", "Nox", "Orin", "Pela", "Quin", "Rysa", "Soren", "Tala",
    "Uris", "Vael", "Wren", "Xan", "Yara", "Zeph",
]

MOTIVATIONS = [
    "Protect the group", "Find food and water", "Acquire shiny objects",
    "Explore the environment", "Find a way out", "Understand what happened here",
    "Stay safe at all costs", "Seek revenge",
]

PERSONALITIES = ["Cautious", "Brave", "Greedy", "Loyal", "Suspicious", "Curious", "Ruthless"]

INVENTORY_CHOICES = [
    ["Paper Money", "Pocket Knife"],
    ["Healing Potion"],
    ["Taser"],
    ["Shiny Coin"],
    ["Rope"],
    ["Torch"],
    ["Old Map"],
]

PERSONALITY_HINTS = {
    "Cautious": "Avoid unnecessary risks; observe, move away, or use healing items first. Survival is primary.",
    "Brave": "Take risks and confront threats. Move toward action. Help others when possible.",
    "Greedy": "Prioritize items and wealth. Pick up everything. Survive alone.",
    "Loyal": "Protect allies and keep promises. Help others; never betray a friend.",
    "Suspicious": "Distrust everyone. Keep distance. Investigate threats secretly before acting.",
    "Curious": "Explore, ask questions, and investigate strange things even if risky.",
    "Ruthless": "Do whatever it takes to survive. Alliances are tools. Betrayal is an option.",
}

MOODS = ["calm", "anxious", "angry", "afraid", "hopeful", "confused", "determined", "suspicious"]

# ── Colors ─────────────────────────────────────────────────────────────────────
COLOR_BG           = (18,  18,  28)
COLOR_GRID         = (30,  30,  45)
COLOR_GOOD         = (60,  200, 80)
COLOR_EVIL         = (220, 60,  60)
COLOR_DEAD         = (90,  90,  90)
COLOR_ITEM         = (200, 180, 80)
COLOR_SPEECH       = (255, 255, 120)
COLOR_SPEECH_EVIL  = (255, 120, 120)
COLOR_STORYTELLER  = (180, 120, 255)
COLOR_UI_TEXT      = (240, 240, 240)
COLOR_UI_PANEL     = (28,  28,  45)
COLOR_HP_BG        = (60,  30,  30)
COLOR_HP_FG        = (60,  200, 60)
COLOR_HP_LOW       = (220, 60,  60)
COLOR_DMG_NUM      = (255, 80,  80)
COLOR_HEAL_NUM     = (80,  255, 120)
COLOR_PARTICLE_ATK = (255, 120, 40)
COLOR_PARTICLE_HIT = (255, 220, 60)
COLOR_SUSPICION    = (255, 200, 50)

# ── Image paths ────────────────────────────────────────────────────────────────
IMAGES_DIR = "images"
DEFAULT_NPC_SPRITE  = "npc_default.png"
DEFAULT_DEAD_SPRITE = "npc_dead.png"
