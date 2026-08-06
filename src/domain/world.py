import math
import random
from uuid import UUID, uuid4

from domain.events import (
    Climate,
    RegionCreated,
    SpeciesGenerated,
    SpeciesProfile,
    WorldCreated,
)
from domain.wordbanks import EPITHETS, HABITATS, PLANTS, PREFIXES, SUFFIXES

WIDTH = 60
HEIGHT = 40

REGIONS = [
    ("Denn Arctogh", (10, 4), Climate(terrain="ice sheet", min_temperature=-35, max_temperature=-2, rainfall="low")),
    ("Boring Tundra", (30, 5), Climate(terrain="tundra", min_temperature=-25, max_temperature=8, rainfall="low")),
    ("Korees", (48, 10), Climate(terrain="mountain", min_temperature=-12, max_temperature=14, rainfall="moderate")),
    ("Wylenn", (8, 17), Climate(terrain="forest", min_temperature=2, max_temperature=20, rainfall="moderate")),
    ("Gloamwoods", (23, 19), Climate(terrain="dark forest", min_temperature=0, max_temperature=16, rainfall="high")),
    ("Trynwyn", (38, 21), Climate(terrain="fungal forest", min_temperature=6, max_temperature=22, rainfall="high")),
    ("Yoonhye Forest", (52, 25), Climate(terrain="temperate forest", min_temperature=4, max_temperature=26, rainfall="moderate")),
    ("Ranatis", (14, 31), Climate(terrain="desert", min_temperature=8, max_temperature=46, rainfall="arid")),
    ("Stragglefaun", (31, 34), Climate(terrain="jungle", min_temperature=20, max_temperature=38, rainfall="torrential")),
    ("Kagotsuma", (48, 36), Climate(terrain="volcanic coast", min_temperature=8, max_temperature=30, rainfall="high")),
]

TRANSPORT_SPEEDS = {"walk": (1.0, 6.0), "swim": (2.0, 8.0), "fly": (5.0, 14.0)}


def assign_tiles(rng: random.Random) -> dict[str, list[tuple[int, int]]]:
    strengths = [rng.uniform(0.85, 1.15) for _ in REGIONS]
    tiles: dict[str, list[tuple[int, int]]] = {name: [] for name, _, _ in REGIONS}

    for y in range(HEIGHT):
        for x in range(WIDTH):
            nearest = min(
                range(len(REGIONS)),
                key=lambda i: math.dist((x, y), REGIONS[i][1]) / strengths[i],
            )
            tiles[REGIONS[nearest][0]].append((x, y))

    return tiles


def _make_name(rng: random.Random, taken: set[str]) -> str:
    while True:
        name = rng.choice(PREFIXES) + rng.choice(SUFFIXES)
        if rng.random() < 0.4:
            name = f"{name} {rng.choice(EPITHETS).capitalize()}"
        if name not in taken:
            taken.add(name)
            return name


def _make_transport(rng: random.Random, climate: Climate) -> str:
    weights = {"walk": 0.6, "swim": 0.15, "fly": 0.25}
    if "coast" in climate.terrain:
        weights = {"walk": 0.4, "swim": 0.4, "fly": 0.2}
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def generate_species(
    rng: random.Random, region_id: UUID, climate: Climate, taken: set[str]
) -> list[SpeciesProfile]:
    profiles = []

    for _ in range(rng.randint(6, 10)):
        diet = rng.choices(
            ["herbivore", "carnivore", "omnivore"], weights=[0.55, 0.30, 0.15]
        )[0]
        transport = _make_transport(rng, climate)
        low, high = TRANSPORT_SPEEDS[transport]

        min_temperature = climate.min_temperature + rng.uniform(-4, 6)
        max_temperature = max(
            climate.max_temperature + rng.uniform(-6, 4), min_temperature + 3
        )

        profiles.append(
            SpeciesProfile(
                id=uuid4(),
                name=_make_name(rng, taken),
                region_id=region_id,
                diet=diet,
                min_temperature=round(min_temperature, 1),
                max_temperature=round(max_temperature, 1),
                habitat=rng.choice(HABITATS),
                food=(
                    rng.sample(PLANTS, rng.randint(1, 3))
                    if diet != "carnivore"
                    else []
                ),
                prey=[],
                transport=transport,
                speed=round(rng.uniform(low, high), 1),
                migratory=rng.random() < (0.6 if transport == "fly" else 0.3),
            )
        )

    hunted = [p.name for p in profiles if p.diet != "carnivore"]
    for profile in profiles:
        if profile.diet != "herbivore" and hunted:
            options = [name for name in hunted if name != profile.name]
            profile.prey = rng.sample(options, min(len(options), rng.randint(1, 3)))

    return profiles


def generate_world(
    seed: int,
) -> tuple[WorldCreated, list[RegionCreated], list[SpeciesGenerated]]:
    rng = random.Random(seed)
    world_id = uuid4()
    tiles = assign_tiles(rng)
    taken: set[str] = set()

    regions = []
    species_events = []

    for name, _, climate in REGIONS:
        region_id = uuid4()
        regions.append(
            RegionCreated(
                world_id=world_id,
                region_id=region_id,
                name=name,
                slug=name.lower().replace(" ", "-"),
                climate=climate,
                tiles=tiles[name],
            )
        )
        species_events.append(
            SpeciesGenerated(
                world_id=world_id,
                region_id=region_id,
                region_name=name,
                species=generate_species(rng, region_id, climate, taken),
            )
        )

    world = WorldCreated(world_id=world_id, seed=seed, width=WIDTH, height=HEIGHT)
    return world, regions, species_events
