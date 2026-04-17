"""particles.py — Particle emitter, floating damage numbers, and animated sprites."""

import math
import time
import os
import config

try:
    import pygame
    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False

try:
    from PIL import Image as PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


# ── Floating number ───────────────────────────────────────────────────────────

class FloatingNumber:
    """A damage or heal number that rises and fades."""

    def __init__(self, value: int, x: float, y: float, is_heal: bool = False):
        self.value = value
        self.x = float(x)
        self.y = float(y)
        self.vy = -1.5          # pixels per frame upward
        self.alpha = 255
        self.fade_rate = 6
        self.color = config.COLOR_HEAL_NUM if is_heal else config.COLOR_DMG_NUM
        self._done = False

    def update(self):
        self.y += self.vy
        self.alpha = max(0, self.alpha - self.fade_rate)
        if self.alpha == 0:
            self._done = True

    @property
    def done(self) -> bool:
        return self._done

    def draw(self, surface, font):
        if not _PYGAME_AVAILABLE or self._done:
            return
        surf = font.render(str(self.value), True, self.color)
        surf.set_alpha(self.alpha)
        surface.blit(surf, (int(self.x), int(self.y)))


# ── Attack particle ───────────────────────────────────────────────────────────

class AttackParticle:
    """A single particle flying from attacker to target."""

    def __init__(self, sx: float, sy: float, tx: float, ty: float,
                 color=None, speed: float = 8.0):
        self.x = float(sx)
        self.y = float(sy)
        self.tx = float(tx)
        self.ty = float(ty)
        dist = math.hypot(tx - sx, ty - sy) or 1
        self.vx = (tx - sx) / dist * speed
        self.vy = (ty - sy) / dist * speed
        self.color = color or config.COLOR_PARTICLE_ATK
        self.alpha = 255
        self._done = False
        self.radius = 3

    def update(self):
        self.x += self.vx
        self.y += self.vy
        dx = self.tx - self.x
        dy = self.ty - self.y
        if math.hypot(dx, dy) < abs(self.vx) + abs(self.vy):
            self._done = True
        self.alpha = max(0, self.alpha - 15)

    @property
    def done(self) -> bool:
        return self._done

    def draw(self, surface):
        if not _PYGAME_AVAILABLE or self._done:
            return
        import pygame
        s = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, self.alpha), (self.radius, self.radius), self.radius)
        surface.blit(s, (int(self.x) - self.radius, int(self.y) - self.radius))


class ParticleEmitter:
    """Manages multiple particles and floating numbers."""

    def __init__(self):
        self.particles: list[AttackParticle] = []
        self.numbers: list[FloatingNumber] = []

    def spawn_attack(self, sx, sy, tx, ty, n: int = 5, color=None):
        import random
        for _ in range(n):
            jitter_x = random.uniform(-4, 4)
            jitter_y = random.uniform(-4, 4)
            self.particles.append(
                AttackParticle(sx, sy, tx + jitter_x, ty + jitter_y,
                               color=color or config.COLOR_PARTICLE_ATK)
            )

    def spawn_hit(self, sx, sy, tx, ty, n: int = 8):
        self.spawn_attack(sx, sy, tx, ty, n=n, color=config.COLOR_PARTICLE_HIT)

    def spawn_number(self, value: int, x: float, y: float, is_heal: bool = False):
        self.numbers.append(FloatingNumber(value, x, y, is_heal=is_heal))

    def update(self):
        for p in self.particles:
            p.update()
        for n in self.numbers:
            n.update()
        self.particles = [p for p in self.particles if not p.done]
        self.numbers = [n for n in self.numbers if not n.done]

    def draw(self, surface, font):
        for p in self.particles:
            p.draw(surface)
        for n in self.numbers:
            n.draw(surface, font)


# ── Animated GIF loader ───────────────────────────────────────────────────────

class AnimatedSprite:
    """Load a GIF (using PIL) and return frames as pygame Surfaces."""

    def __init__(self, path: str, scale=None):
        self.frames: list = []
        self.delays: list[int] = []   # ms per frame
        self._current = 0
        self._elapsed = 0.0
        self.loop = True
        self._done = False

        if not _PIL_AVAILABLE or not _PYGAME_AVAILABLE:
            return

        try:
            gif = PILImage.open(path)
            while True:
                frame = gif.convert("RGBA")
                if scale:
                    frame = frame.resize(scale, PILImage.LANCZOS)
                data = frame.tobytes()
                size = frame.size
                import pygame
                surf = pygame.image.fromstring(data, size, "RGBA").convert_alpha()
                self.frames.append(surf)
                delay = gif.info.get("duration", 100)
                self.delays.append(delay)
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass
        except Exception as e:
            print(f"[AnimatedSprite] Could not load {path}: {e}")

    @property
    def valid(self) -> bool:
        return len(self.frames) > 0

    def update(self, dt_ms: float):
        if not self.valid or self._done:
            return
        self._elapsed += dt_ms
        delay = self.delays[self._current] if self.delays else 100
        if self._elapsed >= delay:
            self._elapsed = 0.0
            self._current += 1
            if self._current >= len(self.frames):
                if self.loop:
                    self._current = 0
                else:
                    self._current = len(self.frames) - 1
                    self._done = True

    @property
    def current_frame(self):
        if not self.valid:
            return None
        return self.frames[self._current]

    @property
    def done(self) -> bool:
        return self._done

    def reset(self):
        self._current = 0
        self._elapsed = 0.0
        self._done = False


# ── Sprite sheet helper ───────────────────────────────────────────────────────

class SpriteCache:
    """Load and cache sprites from the images/ directory.

    Priority:
        1. images/<name>.gif  → AnimatedSprite
        2. images/<name>.png  → static pygame Surface
        3. images/npc_default.png → fallback
        4. None → draw a coloured circle procedurally
    """

    def __init__(self, images_dir: str = config.IMAGES_DIR, tile_size: int = 20):
        self.images_dir = images_dir
        self.tile_size = tile_size
        self._cache: dict[str, object] = {}   # name → Surface | AnimatedSprite | None

    def _load(self, name: str, fallback: str = None):
        if not _PYGAME_AVAILABLE:
            return None
        import pygame
        size = (self.tile_size, self.tile_size)
        candidates = []
        if name:
            safe = name.lower().replace(" ", "_")
            candidates += [
                os.path.join(self.images_dir, f"{safe}.gif"),
                os.path.join(self.images_dir, f"{safe}.png"),
            ]
        if fallback:
            candidates.append(os.path.join(self.images_dir, fallback))

        for path in candidates:
            if not os.path.exists(path):
                continue
            if path.endswith(".gif"):
                anim = AnimatedSprite(path, scale=size)
                if anim.valid:
                    return anim
            else:
                try:
                    surf = pygame.image.load(path).convert_alpha()
                    surf = pygame.transform.scale(surf, size)
                    return surf
                except Exception as e:
                    print(f"[SpriteCache] Could not load {path}: {e}")
        return None

    def get_npc(self, sprite_name: str, is_dead: bool = False):
        key = sprite_name + ("_dead" if is_dead else "")
        if key not in self._cache:
            if is_dead:
                self._cache[key] = self._load(sprite_name + "_dead",
                                               fallback=config.DEFAULT_DEAD_SPRITE)
            else:
                self._cache[key] = self._load(sprite_name,
                                               fallback=config.DEFAULT_NPC_SPRITE)
        return self._cache.get(key)

    def get_item(self, item_name: str):
        key = "item_" + item_name
        if key not in self._cache:
            safe = item_name.lower().replace(" ", "_")
            self._cache[key] = self._load(safe)
        return self._cache.get(key)

    def get_ambient(self, name: str):
        """Ambient animations like campfire (loop indefinitely)."""
        key = "ambient_" + name
        if key not in self._cache:
            self._cache[key] = self._load(name)
        return self._cache.get(key)

    def update_animations(self, dt_ms: float):
        for val in self._cache.values():
            if isinstance(val, AnimatedSprite):
                val.update(dt_ms)
