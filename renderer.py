"""renderer.py — Pygame rendering layer for NPC Sim v2.

Runs in a separate thread.  Reads from SimState (read-only except for
selecting NPCs on click).  All drawing happens here; no sim logic.
"""

import math
import threading
import time
import pygame
import config
from particles import ParticleEmitter, SpriteCache


class Renderer:
    """Pygame window that visualises the simulation."""

    PANEL_W = 280       # right-side inspector panel width
    LOG_H   = 160       # bottom log panel height

    def __init__(self, state, command_queue=None):
        self.state = state
        self.command_queue = command_queue   # optional queue for UI→renderer commands
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

        # Camera
        self.zoom: float = config.DEFAULT_ZOOM
        self.cam_x: float = 0.0
        self.cam_y: float = 0.0
        self._dragging = False
        self._drag_start = (0, 0)
        self._cam_start = (0.0, 0.0)

        # Particles / effects
        self.emitter = ParticleEmitter()
        self._prev_health: dict[str, int] = {}    # for detecting damage

        # Sprites
        self.sprites: SpriteCache | None = None
        self._font_sm: pygame.font.Font | None = None
        self._font_md: pygame.font.Font | None = None
        self._font_lg: pygame.font.Font | None = None

        self._last_time = time.time()

    # ── Public control ────────────────────────────────────────────────────────

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._main, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Main render loop ──────────────────────────────────────────────────────

    def _main(self):
        pygame.init()
        total_w = config.SCREEN_W + self.PANEL_W
        total_h = config.SCREEN_H + self.LOG_H
        screen = pygame.display.set_mode((total_w, total_h), pygame.RESIZABLE)
        pygame.display.set_caption("NPC Simulation v2")

        self._font_sm = pygame.font.SysFont("consolas", 13)
        self._font_md = pygame.font.SysFont("consolas", 16)
        self._font_lg = pygame.font.SysFont("consolas", 22, bold=True)
        self.sprites = SpriteCache(config.IMAGES_DIR,
                                    tile_size=int(config.BASE_SCALE * 1.8))

        clock = pygame.time.Clock()

        while not self._stop.is_set():
            now = time.time()
            dt_ms = (now - self._last_time) * 1000
            self._last_time = now

            # ── Events ────────────────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._stop.set()
                    break
                self._handle_event(event, screen)

            # ── Process command queue ─────────────────────────────────────────
            if self.command_queue:
                while not self.command_queue.empty():
                    cmd = self.command_queue.get_nowait()
                    self._handle_command(cmd)

            # ── Get snapshot ──────────────────────────────────────────────────
            snap = self.state.snapshot()

            # ── Detect damage events for particles ────────────────────────────
            self._detect_damage_events(snap)

            # ── Update particles ──────────────────────────────────────────────
            self.emitter.update()
            if self.sprites:
                self.sprites.update_animations(dt_ms)

            # ── Clear ─────────────────────────────────────────────────────────
            w, h = screen.get_size()
            world_w = w - self.PANEL_W
            world_h = h - self.LOG_H

            screen.fill(config.COLOR_BG)

            # ── World area ────────────────────────────────────────────────────
            world_surf = screen.subsurface(pygame.Rect(0, 0, world_w, world_h))
            self._draw_world(world_surf, snap, dt_ms)

            # ── Right inspector panel ─────────────────────────────────────────
            panel_surf = screen.subsurface(pygame.Rect(world_w, 0, self.PANEL_W, world_h))
            self._draw_inspector(panel_surf, snap)

            # ── Bottom log panel ───────────────────────────────────────────────
            log_surf = screen.subsurface(pygame.Rect(0, world_h, w, self.LOG_H))
            self._draw_log(log_surf, snap)

            # ── Victory overlay ────────────────────────────────────────────────
            if snap["victory"]:
                self._draw_victory(screen, snap["victory"])

            pygame.display.flip()
            clock.tick(config.FPS)

        pygame.quit()

    # ── Event handling ────────────────────────────────────────────────────────

    def _handle_event(self, event, screen):
        state = self.state
        w, h = screen.get_size()
        world_w = w - self.PANEL_W
        world_h = h - self.LOG_H

        if event.type == pygame.MOUSEWHEEL:
            self.zoom = max(config.MIN_ZOOM,
                            min(config.MAX_ZOOM, self.zoom + event.y * 0.1))

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            if mx < world_w and my < world_h:
                if event.button == 2:   # middle mouse drag
                    self._dragging = True
                    self._drag_start = (mx, my)
                    self._cam_start = (self.cam_x, self.cam_y)
                elif event.button == 1:
                    # Click to select NPC
                    snap = self.state.snapshot()
                    clicked = self._pick_npc(mx, my, snap["characters"])
                    with state._lock:
                        state.selected_npc = clicked

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self._dragging = False

        elif event.type == pygame.MOUSEMOTION:
            if self._dragging:
                mx, my = event.pos
                dx = mx - self._drag_start[0]
                dy = my - self._drag_start[1]
                self.cam_x = self._cam_start[0] - dx
                self.cam_y = self._cam_start[1] - dy

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                state.paused = not state.paused
            elif event.key == pygame.K_PLUS or event.key == pygame.K_EQUALS:
                self.zoom = min(config.MAX_ZOOM, self.zoom + 0.1)
            elif event.key == pygame.K_MINUS:
                self.zoom = max(config.MIN_ZOOM, self.zoom - 0.1)
            elif event.key == pygame.K_r:
                self.cam_x = 0.0
                self.cam_y = 0.0
                self.zoom = config.DEFAULT_ZOOM

    def _handle_command(self, cmd: dict):
        if cmd.get("type") == "set_zoom":
            self.zoom = max(config.MIN_ZOOM, min(config.MAX_ZOOM, cmd["value"]))
        elif cmd.get("type") == "center_npc":
            npc = cmd.get("npc")
            if npc:
                scale = config.BASE_SCALE * self.zoom
                self.cam_x = npc.x * scale - config.SCREEN_W / 2
                self.cam_y = npc.y * scale - config.SCREEN_H / 2

    def _pick_npc(self, mx, my, characters):
        """Return the NPC closest to click, or None."""
        best, best_d = None, 999
        for c in characters:
            sx, sy = self._world_to_screen(c.x, c.y)
            d = math.hypot(mx - sx, my - sy)
            if d < 20 and d < best_d:
                best, best_d = c, d
        return best

    # ── World drawing ─────────────────────────────────────────────────────────

    def _world_to_screen(self, wx, wy):
        scale = config.BASE_SCALE * self.zoom
        sx = wx * scale - self.cam_x
        sy = wy * scale - self.cam_y
        return int(sx), int(sy)

    def _draw_world(self, surf, snap, dt_ms):
        scale = config.BASE_SCALE * self.zoom
        world = snap["world"]
        if world is None:
            return

        # Grid
        surf.fill(config.COLOR_BG)
        grid_col = config.COLOR_GRID
        for gx in range(0, world.size + 1, 5):
            sx, sy = self._world_to_screen(gx, 0)
            ex, ey = self._world_to_screen(gx, world.size)
            pygame.draw.line(surf, grid_col, (sx, sy), (ex, ey), 1)
        for gy in range(0, world.size + 1, 5):
            sx, sy = self._world_to_screen(0, gy)
            ex, ey = self._world_to_screen(world.size, gy)
            pygame.draw.line(surf, grid_col, (sx, sy), (ex, ey), 1)

        # Items
        for item in world.items:
            ix, iy = self._world_to_screen(item.x, item.y)
            sprite = self.sprites.get_item(item.sprite_name) if self.sprites else None
            if sprite:
                surf.blit(sprite, (ix - scale//2, iy - scale//2))
            else:
                r = max(4, int(scale * 0.3))
                pygame.draw.rect(surf, config.COLOR_ITEM,
                                 (ix - r, iy - r, r*2, r*2))
            label = self._font_sm.render(item.name, True, (220, 210, 150))
            surf.blit(label, (ix + r + 2, iy - 6))

        # Dead NPCs (tombstones)
        for c in snap["dead_characters"]:
            dx, dy = self._world_to_screen(c.x, c.y)
            sprite = self.sprites.get_npc(c.sprite_name, is_dead=True) if self.sprites else None
            if sprite:
                surf.blit(sprite, (dx - scale//2, dy - scale//2))
            else:
                pygame.draw.polygon(surf, config.COLOR_DEAD,
                                    [(dx, dy-8), (dx-6, dy+6), (dx+6, dy+6)])
            name_surf = self._font_sm.render(c.name[:12], True, (140, 140, 140))
            surf.blit(name_surf, (dx + 8, dy - 4))

        # Live NPCs
        for c in snap["characters"]:
            cx, cy = self._world_to_screen(c.x, c.y)
            color = config.COLOR_EVIL if c.is_evil else config.COLOR_GOOD
            sprite = self.sprites.get_npc(c.sprite_name) if self.sprites else None

            if sprite is None:
                r = max(5, int(scale * 0.4))
                pygame.draw.circle(surf, color, (cx, cy), r)
                # Mood ring
                mood_col = self._mood_color(c.mood)
                pygame.draw.circle(surf, mood_col, (cx, cy), r, 2)
            else:
                import pygame as _pg
                if hasattr(sprite, "current_frame"):
                    frame = sprite.current_frame
                    if frame:
                        surf.blit(frame, (cx - frame.get_width()//2,
                                          cy - frame.get_height()//2))
                else:
                    surf.blit(sprite, (cx - sprite.get_width()//2,
                                       cy - sprite.get_height()//2))

            # HP bar
            self._draw_hp_bar(surf, cx, cy - int(scale * 0.6), c.health, c.max_health)

            # Name tag
            name_col = (255, 180, 180) if c.is_evil else (200, 255, 200)
            name_surf = self._font_sm.render(f"{c.name}", True, name_col)
            surf.blit(name_surf, (cx + 8, cy - 6))

            # Suspicion indicator
            high_sus = [(k, v) for k, v in c.memory_system.suspicions.items() if v >= 5]
            if high_sus:
                sus_surf = self._font_sm.render("!", True, config.COLOR_SUSPICION)
                surf.blit(sus_surf, (cx - 8, cy - int(scale * 0.7)))

            # Last dialogue (speech bubble above head)
            if c.last_dialogue:
                self._draw_speech_bubble(surf, cx, cy - int(scale * 0.8),
                                          c.last_dialogue[:60], c.is_evil)

        # World speeches
        for sp in world.speeches:
            if sp.ttl > 0:
                sx, sy = self._world_to_screen(sp.source.x, sp.source.y)
                txt_surf = self._font_sm.render(sp.text[:50], True, config.COLOR_STORYTELLER)
                surf.blit(txt_surf, (sx, sy - 28))

        # Particles
        self.emitter.draw(surf, self._font_sm)

        # Turn / pause overlay
        turn_txt = self._font_lg.render(
            f"Turn {snap['turn']}  |  NPCs: {len(snap['characters'])}",
            True, (200, 200, 255)
        )
        surf.blit(turn_txt, (8, 6))
        if self.state.paused:
            pause_surf = self._font_lg.render("⏸ PAUSED", True, (255, 220, 60))
            surf.blit(pause_surf, (8, 30))

    def _draw_hp_bar(self, surf, cx, cy, hp, max_hp, width=30, height=4):
        ratio = max(0.0, hp / max(1, max_hp))
        bg_rect = pygame.Rect(cx - width//2, cy, width, height)
        pygame.draw.rect(surf, config.COLOR_HP_BG, bg_rect)
        fg_col = config.COLOR_HP_FG if ratio > 0.35 else config.COLOR_HP_LOW
        fg_rect = pygame.Rect(cx - width//2, cy, int(width * ratio), height)
        pygame.draw.rect(surf, fg_col, fg_rect)

    def _draw_speech_bubble(self, surf, cx, cy, text, is_evil=False):
        col = config.COLOR_SPEECH_EVIL if is_evil else config.COLOR_SPEECH
        txt = self._font_sm.render(text, True, col)
        w, h = txt.get_size()
        pad = 4
        bubble = pygame.Surface((w + pad*2, h + pad*2), pygame.SRCALPHA)
        bubble.fill((0, 0, 0, 140))
        bubble.blit(txt, (pad, pad))
        surf.blit(bubble, (cx - (w + pad*2)//2, cy - h - pad*2))

    def _mood_color(self, mood: str):
        palette = {
            "calm": (100, 200, 100),
            "anxious": (200, 200, 80),
            "angry": (220, 60, 60),
            "afraid": (200, 80, 200),
            "hopeful": (80, 200, 220),
            "confused": (180, 180, 100),
            "determined": (80, 140, 220),
            "suspicious": (220, 180, 40),
        }
        return palette.get(mood, (160, 160, 160))

    # ── Inspector panel ───────────────────────────────────────────────────────

    def _draw_inspector(self, surf, snap):
        surf.fill(config.COLOR_UI_PANEL)
        y = 8
        npc = snap.get("selected_npc")
        fn = self._font_sm
        fm = self._font_md

        def line(text, color=(220, 220, 220), font=None):
            nonlocal y
            f = font or fn
            rendered = f.render(text, True, color)
            surf.blit(rendered, (6, y))
            y += rendered.get_height() + 2

        def divider():
            nonlocal y
            pygame.draw.line(surf, (60, 60, 90), (4, y), (self.PANEL_W - 8, y))
            y += 4

        line("Inspector", (180, 180, 255), fm)
        divider()

        if npc is None:
            line("Click an NPC to inspect", (140, 140, 160))
            line("", )
            line("[SPACE] Pause/Resume")
            line("[+/-]   Zoom")
            line("[R]     Reset camera")
            line("[MMB]   Pan camera")
            line("[Wheel] Zoom camera")
            return

        col = (255, 120, 120) if npc.is_evil else (120, 255, 160)
        label = " [EVIL]" if npc.is_evil else " [good]"
        line(npc.name + label, col, fm)
        line(f"HP: {npc.health}/{npc.max_health}  Cond: {npc.condition}")
        line(f"Pos: {npc.x},{npc.y}  Mood: {npc.mood}", self._mood_color(npc.mood))
        divider()
        line("Personality:", (180, 180, 255))
        line(f"  {npc.personality}")
        line("Short-term goal:", (180, 180, 255))
        for part in self._wrap(npc.short_term_goal or "—", 32):
            line(f"  {part}")
        line("Long-term goal:", (180, 180, 255))
        for part in self._wrap(npc.long_term_goal or "—", 32):
            line(f"  {part}")
        divider()
        line("Inventory:", (180, 180, 255))
        if npc.inventory:
            for item in npc.inventory[:6]:
                line(f"  · {item}")
        else:
            line("  (empty)")
        divider()
        line("Meters:", (180, 180, 255))
        line(f"  Hunger: {int(npc.hunger*100)}%  Fear: {int(npc.fear_level*100)}%")
        line(f"  Curiosity: {int(npc.curiosity*100)}%")
        divider()
        line("Relationships:", (180, 180, 255))
        rel = npc.memory_system.get_relationship_summary()
        for part in self._wrap(rel or "None yet", 34):
            line(f"  {part}")
        divider()
        line("Recent memories:", (180, 180, 255))
        summary = npc.memory_system.get_summary(6)
        for part in self._wrap(summary, 34):
            line(f"  {part}")
        divider()
        line("Internal monologue:", (160, 120, 200))
        mono = npc.memory_system.get_monologue_summary(3)
        for part in self._wrap(mono or "(silent)", 34):
            line(f"  {part}", (160, 120, 200))

    # ── Log panel ─────────────────────────────────────────────────────────────

    def _draw_log(self, surf, snap):
        surf.fill((12, 12, 20))
        pygame.draw.line(surf, (50, 50, 80), (0, 0), (surf.get_width(), 0))
        fn = self._font_sm
        lines = snap["log_lines"]
        max_lines = surf.get_height() // (fn.get_height() + 2)
        visible = lines[-max_lines:]
        y = 4
        for txt in visible:
            col = (255, 120, 120) if "attack" in txt.lower() or "killed" in txt.lower() \
                  else (180, 220, 255) if txt.startswith("[Storyteller]") \
                  else (200, 200, 200)
            rendered = fn.render(txt[:120], True, col)
            surf.blit(rendered, (4, y))
            y += rendered.get_height() + 2

    # ── Victory overlay ───────────────────────────────────────────────────────

    def _draw_victory(self, screen, victory: str):
        w, h = screen.get_size()
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        col = (180, 20, 20, 160) if victory == "evil" else (20, 160, 60, 160)
        overlay.fill(col)
        screen.blit(overlay, (0, 0))
        msg = "EVIL WINS" if victory == "evil" else "GOOD TRIUMPHS"
        txt = self._font_lg.render(msg, True, (255, 255, 255))
        screen.blit(txt, (w//2 - txt.get_width()//2, h//2 - txt.get_height()//2))
        sub = self._font_md.render("Press SPACE or close window", True, (220, 220, 220))
        screen.blit(sub, (w//2 - sub.get_width()//2, h//2 + 30))

    # ── Damage event detection ────────────────────────────────────────────────

    def _detect_damage_events(self, snap):
        for c in snap["characters"]:
            prev = self._prev_health.get(c.name, c.health)
            if c.health < prev:
                dmg = prev - c.health
                sx, sy = self._world_to_screen(c.x, c.y)
                self.emitter.spawn_number(dmg, sx + 5, sy - 20, is_heal=False)
                # Attacker particle (guess: someone nearby who is evil or attacked)
                for other in snap["characters"]:
                    if other is not c and other.is_evil:
                        ox, oy = self._world_to_screen(other.x, other.y)
                        self.emitter.spawn_attack(ox, oy, sx, sy)
                        break
            elif c.health > prev:
                heal = c.health - prev
                sx, sy = self._world_to_screen(c.x, c.y)
                self.emitter.spawn_number(heal, sx + 5, sy - 20, is_heal=True)
            self._prev_health[c.name] = c.health

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _wrap(text: str, width: int) -> list[str]:
        if not text:
            return [""]
        words = text.split()
        lines, current = [], ""
        for w in words:
            if len(current) + len(w) + 1 <= width:
                current = (current + " " + w).strip()
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines or [""]
