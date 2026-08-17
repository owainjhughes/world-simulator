import random
from uuid import UUID, uuid4

from domain.atlas import HEIGHT, MAP_ROWS, OCEAN, REGIONS, WIDTH
from domain.events import (
    Climate,
    RegionCreated,
    SpeciesGenerated,
    SpeciesProfile,
    WorldCreated,
)
from domain.wordbanks import EPITHETS, HABITATS, PREFIXES, SUFFIXES

TRANSPORT_SPEEDS = {"walk": (1.0, 6.0), "swim": (2.0, 8.0), "fly": (5.0, 14.0)}


def slug_for(name: str) -> str:
    return name.lower().replace(" ", "-")


def assign_regions() -> dict[str, list[tuple[int, int]]]:
    name_of = {key: name for key, name, _, _, _ in REGIONS}
    tiles: dict[str, list[tuple[int, int]]] = {name: [] for name in name_of.values()}

    for y, row in enumerate(MAP_ROWS):
        for x, key in enumerate(row):
            if key != OCEAN:
                tiles[name_of[key]].append((x, y))

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
    if "coast" in climate.terrain or "estuary" in climate.terrain:
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

        min_temperature = climate.min_temperature + rng.uniform(-6, 1)
        max_temperature = max(
            climate.max_temperature + rng.uniform(-1, 6), min_temperature + 3
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
                    rng.sample(climate.plants, min(len(climate.plants), rng.randint(1, 3)))
                    if diet != "carnivore"
                    else []
                ),
                prey=[],
                transport=transport,
                speed=round(rng.uniform(low, high), 1),
                migratory=rng.random() < (0.6 if transport == "fly" else 0.3),
            )
        )

    return profiles


def wire_food_web(rng: random.Random, profiles: list[SpeciesProfile]) -> None:
    hunted = [p for p in profiles if p.diet != "carnivore"]

    for profile in profiles:
        if profile.diet == "herbivore":
            continue
        options = [
            p
            for p in hunted
            if p.name != profile.name
            and p.speed < profile.speed + 2
            and p.min_temperature <= profile.max_temperature
            and profile.min_temperature <= p.max_temperature
        ]
        neighbours = [p.name for p in options if p.region_id == profile.region_id]
        elsewhere = [p.name for p in options if p.region_id != profile.region_id]

        wanted = rng.randint(3, 6)
        profile.prey = rng.sample(neighbours, min(len(neighbours), wanted))
        profile.prey += rng.sample(
            elsewhere, min(len(elsewhere), wanted - len(profile.prey))
        )


def generate_world(
    seed: int,
) -> tuple[WorldCreated, list[RegionCreated], list[SpeciesGenerated]]:
    rng = random.Random(seed)
    world_id = uuid4()
    tiles = assign_regions()
    taken: set[str] = set()

    regions = []
    species_events = []

    for _, name, continent, colour, climate in REGIONS:
        region_id = uuid4()
        regions.append(
            RegionCreated(
                world_id=world_id,
                region_id=region_id,
                name=name,
                slug=slug_for(name),
                continent=continent,
                colour=colour,
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

    wire_food_web(rng, [p for event in species_events for p in event.species])

    world = WorldCreated(
        world_id=world_id,
        seed=seed,
        width=WIDTH,
        height=HEIGHT,
        regions=len(regions),
        species=sum(len(event.species) for event in species_events),
    )
    return world, regions, species_events
