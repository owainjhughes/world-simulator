import colorsys
import hashlib
import math
from dataclasses import dataclass

FADE_SECONDS = 0.6
DEFAULT_STRIDE = 2.0
MIN_STRIDE = 0.4
MAX_STRIDE = 6.0
SPREAD = 0.22
DRIFT = 0.08

# Sprites face right. Each animal has two frames: "1" cells only show in the
# first, "2" cells only in the second. "p" cells take the species' markings,
# "x" cells are ears, horns or fins that only some species grow.
SHAPES = {
    "walk": [
        [
            "......x.",
            ".....bbb",
            ".....beb",
            "bppppbb.",
            ".ppppp..",
            ".aaaaa..",
            ".1.1.2.2",
            "1.1.2.2.",
        ],
        [
            "........",
            "....x...",
            "..bbbbb.",
            ".ppppeb.",
            "bpppppbb",
            ".aaaaaa.",
            "..1..1..",
            ".2..2...",
        ],
        [
            "........",
            "......bb",
            "......eb",
            "b.....b.",
            "bppppbb.",
            ".ppppp..",
            "..1.1...",
            ".2...2..",
        ],
    ],
    "swim": [
        [
            "........",
            "...xx...",
            "1.ppppb.",
            "bbppppeb",
            "2.aaaab.",
            "...xx...",
            "........",
            "........",
        ],
        [
            "........",
            "....x...",
            "1.pppbb.",
            "bbpppbeb",
            "bbaaaabb",
            "2.aaaa..",
            "........",
            "........",
        ],
    ],
    "fly": [
        [
            "1.....1.",
            ".11..11.",
            "..pbbbb.",
            "..ppbeb.",
            ".22aa22.",
            "2.....2.",
            "........",
            "........",
        ],
        [
            "........",
            "11...11.",
            ".1pbb1..",
            "..ppbeb.",
            "..aab...",
            ".22.22..",
            "........",
            "........",
        ],
    ],
}
EYES = {
    "herbivore": (20, 20, 20),
    "omnivore": (255, 196, 40),
    "carnivore": (230, 30, 30),
}


def _digest(text: str) -> bytes:
    return hashlib.sha256(text.encode()).digest()


@dataclass(frozen=True)
class Look:
    rows: tuple[str, ...]
    body: tuple[int, int, int]
    accent: tuple[int, int, int]
    dark: tuple[int, int, int]
    eye: tuple[int, int, int]
    markings: frozenset[tuple[int, int]]
    crest: bool


def _rgb(hue: float, lightness: float, saturation: float) -> tuple[int, int, int]:
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return round(red * 255), round(green * 255), round(blue * 255)


# Every species gets its own sprite, the same one every time it is seen.
def look_for(species: str, diet: str, transport: str) -> Look:
    seed = _digest(species)
    shapes = SHAPES.get(transport, SHAPES["walk"])
    rows = tuple(shapes[seed[0] % len(shapes)])
    hue = seed[1] / 255
    markings = frozenset(
        (x, y)
        for y, row in enumerate(rows)
        for x, cell in enumerate(row)
        if cell == "p" and _digest(f"{species}:{x}:{y}")[0] % 3 == 0
    )
    return Look(
        rows=rows,
        body=_rgb(hue, 0.55, 0.65),
        accent=_rgb((hue + 0.08) % 1, 0.78, 0.55),
        dark=_rgb(hue, 0.22, 0.5),
        eye=EYES.get(diet, EYES["herbivore"]),
        markings=markings,
        crest=seed[2] % 2 == 0,
    )


# The coloured pixels of one animation frame, as (x, y, colour).
def pixels(look: Look, frame: int) -> list[tuple[int, int, tuple[int, int, int]]]:
    drawn = []
    for y, row in enumerate(look.rows):
        for x, cell in enumerate(row):
            if cell == "b":
                colour = look.body
            elif cell == "p":
                colour = look.dark if (x, y) in look.markings else look.body
            elif cell == "a":
                colour = look.accent
            elif cell == "e":
                colour = look.eye
            elif cell == "x" and look.crest:
                colour = look.dark
            elif cell == "1" and frame == 0 or cell == "2" and frame == 1:
                colour = look.dark
            else:
                continue
            drawn.append((x, y, colour))
    return drawn


def _phase(creature_id: str, salt: str) -> float:
    return _digest(f"{creature_id}:{salt}")[0] / 255


def _ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


@dataclass
class Sprite:
    id: str
    region: str
    species: str
    diet: str
    transport: str
    start: tuple[float, float]
    target: tuple[float, float]
    moved_at: float
    stride: float
    born_at: float
    died_at: float | None = None
    facing: int = 1

    # Where the sprite is drawn at a moment, in tile units, centre of its tile.
    def place(self, at: float) -> tuple[float, float]:
        t = _ease((at - self.moved_at) / self.stride)
        x = self.start[0] + (self.target[0] - self.start[0]) * t
        y = self.start[1] + (self.target[1] - self.start[1]) * t
        drift_x = math.sin(at * 0.9 + _phase(self.id, "dx") * math.tau) * DRIFT
        drift_y = math.cos(at * 0.7 + _phase(self.id, "dy") * math.tau) * DRIFT
        return x + drift_x, y + drift_y

    # Vertical bounce in tile units: fliers hover, walkers hop while moving.
    def bob(self, at: float) -> float:
        phase = _phase(self.id, "bob") * math.tau
        if self.transport == "fly":
            return math.sin(at * 4 + phase) * 0.12 - 0.15
        if self.transport == "swim":
            return math.sin(at * 2 + phase) * 0.05
        moving = 0 < at - self.moved_at < self.stride and self.start != self.target
        return -abs(math.sin(at * 9 + phase)) * 0.1 if moving else 0.0

    def frame(self, at: float) -> int:
        speed = 6 if self.transport == "fly" else 4
        return int(at * speed + _phase(self.id, "frame") * 2) % 2

    def opacity(self, at: float) -> float:
        fade_in = min(1.0, (at - self.born_at) / FADE_SECONDS)
        if self.died_at is None:
            return max(0.0, fade_in)
        return max(0.0, min(fade_in, 1 - (at - self.died_at) / FADE_SECONDS))


# A resting spot within the tile, so animals sharing a tile do not stack.
def _spot(creature_id: str, x: int, y: int) -> tuple[float, float]:
    return (
        x + 0.5 + (_phase(creature_id, "sx") - 0.5) * 2 * SPREAD,
        y + 0.5 + (_phase(creature_id, "sy") - 0.5) * 2 * SPREAD,
    )


# Tracks every creature seen in a census and glides it between sightings.
class Herd:

    def __init__(self) -> None:
        self.sprites: dict[str, Sprite] = {}
        self.last_census: dict[str, float] = {}
        self.strides: dict[str, float] = {}

    def observe(self, region: str, sightings: list[dict], at: float) -> None:
        previous = self.last_census.get(region)
        if previous is not None:
            interval = min(MAX_STRIDE, max(MIN_STRIDE, at - previous))
            self.strides[region] = interval
        self.last_census[region] = at
        stride = self.strides.get(region, DEFAULT_STRIDE)

        seen = set()
        for sighting in sightings:
            creature_id = str(sighting["id"])
            seen.add(creature_id)
            target = _spot(creature_id, sighting["x"], sighting["y"])
            sprite = self.sprites.get(creature_id)
            if sprite is None or sprite.died_at is not None:
                self.sprites[creature_id] = Sprite(
                    id=creature_id,
                    region=region,
                    species=sighting["species"],
                    diet=sighting["diet"],
                    transport=sighting["transport"],
                    start=target,
                    target=target,
                    moved_at=at,
                    stride=stride,
                    born_at=at,
                )
                continue
            sprite.start = sprite.place(at)
            sprite.target = target
            sprite.moved_at = at
            sprite.stride = stride
            sprite.region = region
            if abs(target[0] - sprite.start[0]) > 0.05:
                sprite.facing = 1 if target[0] > sprite.start[0] else -1

        for sprite in self.sprites.values():
            if sprite.region == region and sprite.id not in seen and sprite.died_at is None:
                sprite.died_at = at

    # Live and fading sprites, dropping any that have finished fading out.
    def visible(self, at: float) -> list[Sprite]:
        gone = [
            creature_id
            for creature_id, sprite in self.sprites.items()
            if sprite.died_at is not None and at - sprite.died_at >= FADE_SECONDS
        ]
        for creature_id in gone:
            del self.sprites[creature_id]
        return sorted(self.sprites.values(), key=lambda sprite: sprite.place(at)[1])

    def nearest(self, x: float, y: float, at: float, reach: float = 0.7) -> Sprite | None:
        best, best_distance = None, reach
        for sprite in self.sprites.values():
            if sprite.died_at is not None:
                continue
            px, py = sprite.place(at)
            distance = math.hypot(px - x, py - y)
            if distance < best_distance:
                best, best_distance = sprite, distance
        return best
