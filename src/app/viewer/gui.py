import asyncio
import hashlib
import json
import math
import time

import pygame

from app.viewer import main as terminal
from app.viewer.herd import Herd, Look, look_for, pixels
from domain.atlas import CONTINENTS, OCEAN_COLOUR

FPS = 30
PANEL = 210
START_SIZE = (1400, 700 + PANEL)
MIN_TILE, MAX_TILE = 4, 40
SPRITE_SIZE = 8
SHALLOWS = (70, 196, 205)
BORDER = (0, 0, 0, 70)
NIGHT = (10, 14, 40)
PANEL_BG = (24, 26, 32)
TEXT = (225, 228, 235)
DIM = (140, 146, 160)
WEATHER = {"rain": (170, 200, 255), "snow": (250, 250, 255), "wind": (230, 236, 240)}

herd = Herd()


def rgb(colour: str) -> tuple[int, int, int]:
    return terminal.rgb(colour)


def grain(x: int, y: int) -> float:
    return hashlib.sha256(f"{x},{y}".encode()).digest()[0] / 255


def varied(colour: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(channel * amount))) for channel in colour)


class View:
    """The camera onto the map: how big a tile is and where the map sits."""

    def __init__(self, width: int, height: int) -> None:
        self.tile = MIN_TILE
        self.offset = [0.0, 0.0]
        self.resize(width, height)

    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, max(1, height - PANEL)
        self.fit()

    def fit(self) -> None:
        columns, rows = len(terminal.world["grid"][0]), len(terminal.world["grid"])
        self.tile = max(MIN_TILE, min(self.width // columns, self.height // rows))
        self.offset = [
            (self.width - columns * self.tile) / 2,
            (self.height - rows * self.tile) / 2,
        ]

    def zoom(self, steps: int, around: tuple[int, int]) -> None:
        tile = max(MIN_TILE, min(MAX_TILE, self.tile + steps * max(1, self.tile // 6)))
        if tile == self.tile:
            return
        x, y = self.to_world(around)
        self.tile = tile
        self.offset = [around[0] - x * tile, around[1] - y * tile]

    def pan(self, dx: int, dy: int) -> None:
        self.offset[0] += dx
        self.offset[1] += dy

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        return self.offset[0] + x * self.tile, self.offset[1] + y * self.tile

    def to_world(self, point: tuple[int, int]) -> tuple[float, float]:
        return (
            (point[0] - self.offset[0]) / self.tile,
            (point[1] - self.offset[1]) / self.tile,
        )

    @property
    def scale(self) -> int:
        return max(1, round(self.tile / 11))


class Painter:
    """Draws the world, caching whatever only changes when the zoom does."""

    def __init__(self) -> None:
        self.font = pygame.font.Font(None, 18)
        self.title = pygame.font.Font(None, 26)
        self.terrain: pygame.Surface | None = None
        self.terrain_tile = 0
        self.sprites: dict[tuple, pygame.Surface] = {}
        self.looks: dict[str, Look] = {}
        self.darkness = 1.0 if terminal.now["night"] else 0.0
        self.shade: pygame.Surface | None = None
        self.region_tiles: dict[str, list[tuple[int, int]]] = {}

    def build_terrain(self, tile: int) -> pygame.Surface:
        grid, owners = terminal.world["grid"], terminal.world["owners"]
        height, width = len(grid), len(grid[0])
        surface = pygame.Surface((width * tile, height * tile))
        for y in range(height):
            for x in range(width):
                colour = rgb(grid[y][x])
                if owners[y][x] is None and self.near_land(x, y):
                    colour = SHALLOWS
                spread = 0.16 if owners[y][x] else 0.05
                shade = 1 - spread / 2 + grain(x, y) * spread
                surface.fill(varied(colour, shade), (x * tile, y * tile, tile, tile))
        if tile >= 6:
            borders = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            for y in range(height):
                for x in range(width):
                    here = owners[y][x]
                    if x + 1 < width and owners[y][x + 1] != here:
                        borders.fill(BORDER, ((x + 1) * tile, y * tile, 1, tile))
                    if y + 1 < height and owners[y + 1][x] != here:
                        borders.fill(BORDER, (x * tile, (y + 1) * tile, tile, 1))
            surface.blit(borders, (0, 0))
        return surface

    def near_land(self, x: int, y: int) -> bool:
        owners = terminal.world["owners"]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if 0 <= ny < len(owners) and 0 <= nx < len(owners[0]) and owners[ny][nx]:
                    return True
        return False

    def sprite(self, species: str, diet: str, transport: str, frame: int, facing: int, scale: int):
        key = (species, frame, facing, scale)
        if key not in self.sprites:
            look = self.looks.setdefault(species, look_for(species, diet, transport))
            surface = pygame.Surface((SPRITE_SIZE * scale, SPRITE_SIZE * scale), pygame.SRCALPHA)
            for x, y, colour in pixels(look, frame):
                surface.fill(colour, (x * scale, y * scale, scale, scale))
            if facing < 0:
                surface = pygame.transform.flip(surface, True, False)
            self.sprites[key] = surface
        return self.sprites[key]

    def draw(self, screen: pygame.Surface, view: View, at: float, mouse) -> None:
        screen.fill(rgb(OCEAN_COLOUR))
        if self.terrain is None or self.terrain_tile != view.tile:
            self.terrain = self.build_terrain(view.tile)
            self.terrain_tile = view.tile
        screen.set_clip((0, 0, view.width, view.height))
        screen.blit(self.terrain, view.to_screen(0, 0))
        self.draw_weather(screen, view, at)
        self.draw_night(screen, view)
        self.draw_creatures(screen, view, at)
        screen.set_clip(None)
        self.draw_panel(screen, view)
        self.draw_tooltip(screen, view, at, mouse)

    def tiles_of(self, slug: str) -> list[tuple[int, int]]:
        if slug not in self.region_tiles:
            owners = terminal.world["owners"]
            self.region_tiles[slug] = [
                (x, y)
                for y, row in enumerate(owners)
                for x, owner in enumerate(row)
                if owner == slug
            ]
        return self.region_tiles[slug]

    def draw_weather(self, screen: pygame.Surface, view: View, at: float) -> None:
        tile = view.tile
        glow = pygame.Surface((tile, tile), pygame.SRCALPHA)
        glow.fill((255, 230, 120, 40))
        for slug, region in terminal.world["regions"].items():
            weather = region["weather"]
            if not weather:
                continue
            for x, y in self.tiles_of(slug):
                left, top = view.to_screen(x, y)
                if left + tile < 0 or top + tile < 0 or left > view.width or top > view.height:
                    continue
                if "sunshine" in weather:
                    screen.blit(glow, (left, top))
                seed = grain(x, y)
                if "rain" in weather:
                    fall = (at * 2.2 + seed) % 1
                    px, py = left + seed * tile, top + fall * tile
                    pygame.draw.line(
                        screen, WEATHER["rain"], (px, py), (px - tile * 0.15, py + tile * 0.35)
                    )
                if "snow" in weather:
                    fall = (at * 0.5 + seed) % 1
                    px = left + ((seed * 3 + math.sin(at * 2 + seed * 9) * 0.15) % 1) * tile
                    py = top + fall * tile
                    pygame.draw.circle(screen, WEATHER["snow"], (px, py), max(1, tile // 10))
                if "wind" in weather and seed < 0.35:
                    drift = (at * 1.5 + seed * 7) % 1
                    px, py = left + drift * tile, top + (seed * 2.5 % 1) * tile
                    pygame.draw.line(screen, WEATHER["wind"], (px, py), (px + tile * 0.6, py))

    def draw_night(self, screen: pygame.Surface, view: View) -> None:
        target = 1.0 if terminal.now["night"] else 0.0
        self.darkness += (target - self.darkness) * 0.05
        if self.darkness < 0.02:
            return
        if self.shade is None or self.shade.get_size() != (view.width, view.height):
            self.shade = pygame.Surface((view.width, view.height), pygame.SRCALPHA)
        self.shade.fill((*NIGHT, round(self.darkness * 130)))
        screen.blit(self.shade, (0, 0))

    def draw_creatures(self, screen: pygame.Surface, view: View, at: float) -> None:
        scale = view.scale
        size = SPRITE_SIZE * scale
        shadow = pygame.Surface((size, max(2, size // 3)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 70), shadow.get_rect())
        for sprite in herd.visible(at):
            x, y = sprite.place(at)
            cx, cy = view.to_screen(x, y)
            if cx < -size or cy < -size or cx > view.width + size or cy > view.height + size:
                continue
            opacity = sprite.opacity(at)
            if opacity <= 0:
                continue
            lift = sprite.bob(at) * view.tile
            if sprite.transport != "swim":
                screen.blit(shadow, (cx - size / 2, cy + size / 2 - shadow.get_height() / 2))
            image = self.sprite(
                sprite.species,
                sprite.diet,
                sprite.transport,
                sprite.frame(at),
                sprite.facing,
                scale,
            )
            if opacity < 1:
                image = image.copy()
                image.set_alpha(round(opacity * 255))
            screen.blit(image, (cx - size / 2, cy - size / 2 + lift))

    def text(self, screen, words: str, where, colour=TEXT, font=None) -> None:
        screen.blit((font or self.font).render(words, True, colour), where)

    def draw_panel(self, screen: pygame.Surface, view: View) -> None:
        top = view.height
        screen.fill(PANEL_BG, (0, top, screen.get_width(), PANEL))
        now = terminal.now
        clock = "night" if now["night"] else "day"
        self.text(
            screen,
            f"Arathia   day {now['day']}  {now['hour']:02d}:00  {now['season']}  ({clock})",
            (12, top + 8),
            font=self.title,
        )
        self.text(
            screen,
            "scroll to zoom · drag to pan · F to fit · Q to quit",
            (screen.get_width() - 330, top + 12),
            DIM,
        )

        column_width = 290
        for index, continent in enumerate(CONTINENTS):
            left = 12 + index * column_width
            self.text(screen, continent, (left, top + 36), DIM)
            members = [
                slug
                for slug in terminal.world["order"]
                if terminal.world["regions"][slug]["continent"] == continent
            ]
            members.sort(key=lambda slug: terminal.world["regions"][slug]["latitude"])
            for row, slug in enumerate(members):
                region = terminal.world["regions"][slug]
                y = top + 54 + row * 16
                screen.fill(DIM, (left - 1, y + 1, 12, 12))
                screen.fill(rgb(region["colour"]), (left, y + 2, 10, 10))
                celsius = "   -" if region["celsius"] is None else f"{region['celsius']:5.1f}C"
                population = "-" if region["population"] is None else str(region["population"])
                weather = " ".join(sorted(region["weather"]))
                self.text(screen, region["name"], (left + 16, y))
                self.text(screen, f"{celsius}  {population:>4}  {weather}", (left + 128, y), DIM)

        left = 12 + len(CONTINENTS) * column_width
        self.text(screen, "World log", (left, top + 36), DIM)
        for row, entry in enumerate(terminal.log):
            self.text(screen, entry, (left, top + 54 + row * 15))

    def draw_tooltip(self, screen: pygame.Surface, view: View, at: float, mouse) -> None:
        if mouse[1] >= view.height:
            return
        x, y = view.to_world(mouse)
        sprite = herd.nearest(x, y, at, reach=max(0.6, SPRITE_SIZE * view.scale / view.tile))
        lines: list[str] = []
        if sprite:
            region = terminal.world["regions"].get(sprite.region, {})
            lines = [
                sprite.species,
                f"{sprite.diet} · {sprite.transport}s · {region.get('name', '')}",
            ]
        else:
            tx, ty = int(x), int(y)
            owners = terminal.world["owners"]
            if 0 <= ty < len(owners) and 0 <= tx < len(owners[0]) and owners[ty][tx]:
                region = terminal.world["regions"][owners[ty][tx]]
                celsius = "" if region["celsius"] is None else f"{region['celsius']:.1f}C"
                lines = [region["name"], f"{region['continent']} {celsius}".strip()]
        if not lines:
            return
        rendered = [self.font.render(line, True, TEXT) for line in lines]
        width = max(line.get_width() for line in rendered) + 12
        height = sum(line.get_height() for line in rendered) + 8
        left = min(mouse[0] + 14, screen.get_width() - width)
        top = min(mouse[1] + 14, view.height - height)
        box = pygame.Surface((width, height), pygame.SRCALPHA)
        box.fill((15, 16, 22, 220))
        screen.blit(box, (left, top))
        for line in rendered:
            screen.blit(line, (left + 6, top + 4))
            top += line.get_height()


def apply_event(routing_key: str, payload: dict, at: float) -> None:
    terminal.apply_event(routing_key, payload)
    if not routing_key.startswith("ecology.census.") or payload["world_id"] != terminal.world["id"]:
        return
    slug = payload.get("region_slug")
    if slug in terminal.world["regions"]:
        herd.observe(slug, payload.get("creatures", []), at)


async def consume(queue) -> None:
    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():
                apply_event(message.routing_key, json.loads(message.body), time.monotonic())


def handle(event, view: View, dragging: list) -> bool:
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.KEYDOWN:
        if event.key in (pygame.K_q, pygame.K_ESCAPE):
            return False
        if event.key == pygame.K_f:
            view.fit()
        elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            view.zoom(1, (view.width // 2, view.height // 2))
        elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            view.zoom(-1, (view.width // 2, view.height // 2))
    elif event.type == pygame.VIDEORESIZE:
        view.resize(event.w, event.h)
    elif event.type == pygame.MOUSEWHEEL:
        view.zoom(event.y, pygame.mouse.get_pos())
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 2, 3):
        dragging[:] = [True]
    elif event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2, 3):
        dragging.clear()
    elif event.type == pygame.MOUSEMOTION and dragging:
        view.pan(*event.rel)
    return True


async def run_window() -> None:
    pygame.display.set_caption("Arathia")
    screen = pygame.display.set_mode(START_SIZE, pygame.RESIZABLE)
    view = View(*screen.get_size())
    painter = Painter()
    dragging: list = []
    frame = 1 / FPS
    while True:
        started = time.monotonic()
        if not all(handle(event, view, dragging) for event in pygame.event.get()):
            return
        painter.draw(screen, view, started, pygame.mouse.get_pos())
        pygame.display.flip()
        await asyncio.sleep(max(0.0, frame - (time.monotonic() - started)))


async def main() -> None:
    queue = await terminal.bind_queue()
    await terminal.load_world()
    pygame.display.init()
    pygame.font.init()
    consumer = asyncio.create_task(consume(queue))
    try:
        await run_window()
    finally:
        consumer.cancel()
        pygame.quit()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
