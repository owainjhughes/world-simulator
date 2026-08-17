import random
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from domain.atlas import MAP_ROWS, OCEAN
from domain.events import Climate, DeathCause, SpeciesProfile
from domain.seasons import HOURS_PER_DAY

HUNGER_PER_HOUR = 1 / 72
STRESS_PER_HOUR = 0.01
RELIEF_PER_HOUR = 0.03
STRESSED_APPETITE = 1.5
CARNIVORE_APPETITE = 0.5
GRAZE_PER_HOUR = 0.25
NOURISHMENT = 3.0
REGROWTH = {
    "arid": 0.002,
    "low": 0.004,
    "moderate": 0.008,
    "high": 0.012,
    "torrential": 0.018,
}
SEASON_GROWTH = {"winter": 0.4, "spring": 1.2, "summer": 1.0, "autumn": 0.8}
TOLERANCE = 3.0
SIGHT = 8
FLEE_SIGHT = 3
FORAGE_SIGHT = 3
FLEE_HUNGER = 0.5
HUNT_HUNGER = 0.5
BARE = 0.3
BREED_HUNGER = 0.4
BREED_AGE = 10 * HOURS_PER_DAY
BREED_COOLDOWN = 3 * HOURS_PER_DAY
HUNTER_BREED_AGE = 20 * HOURS_PER_DAY
HUNTER_BREED_COOLDOWN = 12 * HOURS_PER_DAY
LIFESPAN = (40 * HOURS_PER_DAY, 90 * HOURS_PER_DAY)
CARRYING = {
    rainfall: rate * NOURISHMENT / HUNGER_PER_HOUR for rainfall, rate in REGROWTH.items()
}
START_SHARE = 0.35
PREDATOR_SHARE = 0.12
FOUNDERS = 8
HUNTER_FOUNDERS = 4
SPAWN_WEIGHT = (0.5, 1.5)
SPAWN_CHANCE = 0.5

OCEAN_TILES = {
    (x, y)
    for y, row in enumerate(MAP_ROWS)
    for x, key in enumerate(row)
    if key == OCEAN
}


@dataclass
class Creature:
    id: UUID
    species_id: UUID
    x: int
    y: int
    hunger: float = 0.0
    stress: float = 0.0
    age: int = 0
    lifespan: int = 0
    cooldown: int = 0


@dataclass
class Region:
    region_id: UUID
    climate: Climate
    tiles: list[tuple[int, int]]


@dataclass
class Death:
    species: str
    cause: DeathCause
    killed_by: str | None = None


@dataclass
class StepResult:
    creatures: list[Creature]
    vegetation: list[float]
    born: list[str] = field(default_factory=list)
    deaths: list[Death] = field(default_factory=list)
    extinct: list[str] = field(default_factory=list)
    comfort: dict[str, bool] = field(default_factory=dict)


def allowed_tiles(tiles: list[tuple[int, int]], transport: str) -> list[tuple[int, int]]:
    land = [tuple(tile) for tile in tiles]
    if transport == "walk":
        return land
    shore = {
        (x + dx, y + dy)
        for x, y in land
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        if (x + dx, y + dy) in OCEAN_TILES
    }
    return land + sorted(shore)


def _tolerates(profile: SpeciesProfile, climate: Climate) -> bool:
    return (
        profile.min_temperature <= climate.min_temperature + TOLERANCE
        and profile.max_temperature >= climate.max_temperature - TOLERANCE
    )


def region_suits(profile: SpeciesProfile, climate: Climate) -> bool:
    return _tolerates(profile, climate) and bool(
        set(profile.food) & set(climate.plants)
    )


def hunting_grounds(
    profile: SpeciesProfile, regions: list[Region], present: dict[UUID, set[str]]
) -> list[Region]:
    return [
        region
        for region in regions
        if _tolerates(profile, region.climate)
        and not present[region.region_id].isdisjoint(profile.prey)
    ]


def carrying_capacity(region: Region) -> float:
    return len(region.tiles) * CARRYING[region.climate.rainfall]


def _some_of(rng: random.Random, regions: list[Region]) -> list[Region]:
    return [region for region in regions if rng.random() < SPAWN_CHANCE]


def _share_out(
    rng: random.Random,
    residents: list[SpeciesProfile],
    budget: float,
    founders: int,
) -> dict[UUID, int]:
    weights = {profile.id: rng.uniform(*SPAWN_WEIGHT) for profile in residents}
    total = sum(weights.values())
    counts: dict[UUID, int] = {}
    left = budget

    for profile in residents:
        share = max(founders, round(budget * weights[profile.id] / total))
        if not counts:
            counts[profile.id] = share
        elif left >= founders:
            counts[profile.id] = min(int(left), share)
        else:
            break
        left -= counts[profile.id]

    return counts


def populate(
    rng: random.Random, profiles: list[SpeciesProfile], regions: list[Region]
) -> dict[UUID, list[Creature]]:
    by_id = {profile.id: profile for profile in profiles}
    grazers: dict[UUID, list[SpeciesProfile]] = {
        region.region_id: [] for region in regions
    }

    for profile in profiles:
        if profile.diet == "carnivore":
            continue
        grazers[profile.region_id].insert(0, profile)
        visiting = [
            region
            for region in regions
            if region.region_id != profile.region_id
            and region_suits(profile, region.climate)
        ]
        for region in _some_of(rng, visiting):
            grazers[region.region_id].append(profile)

    counts = {
        region.region_id: _share_out(
            rng,
            grazers[region.region_id],
            carrying_capacity(region) * START_SHARE,
            FOUNDERS,
        )
        for region in regions
    }
    present = {
        region_id: {by_id[species_id].name for species_id in tally}
        for region_id, tally in counts.items()
    }

    hunters: dict[UUID, list[SpeciesProfile]] = {
        region.region_id: [] for region in regions
    }
    for profile in profiles:
        if profile.diet != "carnivore":
            continue
        for region in _some_of(rng, hunting_grounds(profile, regions, present)):
            hunters[region.region_id].append(profile)

    spawned: dict[UUID, list[Creature]] = {}
    for region in regions:
        tally = counts[region.region_id]
        for profile in hunters[region.region_id]:
            prey_base = sum(
                count
                for species_id, count in tally.items()
                if by_id[species_id].name in profile.prey
            )
            pack = round(prey_base * PREDATOR_SHARE)
            if pack >= HUNTER_FOUNDERS:
                tally[profile.id] = pack

        born = []
        for species_id, count in tally.items():
            ground = allowed_tiles(region.tiles, by_id[species_id].transport)
            for _ in range(count):
                lifespan = rng.randint(*LIFESPAN)
                x, y = rng.choice(ground)
                born.append(
                    Creature(
                        id=uuid4(),
                        species_id=species_id,
                        x=x,
                        y=y,
                        age=rng.randint(0, lifespan // 2),
                        lifespan=lifespan,
                    )
                )
        spawned[region.region_id] = born

    return spawned


def census(
    creatures: list[Creature], species: dict[UUID, SpeciesProfile]
) -> dict[str, list[tuple[int, int]]]:
    seen: dict[str, list[tuple[int, int]]] = {
        "herbivores": [],
        "carnivores": [],
        "omnivores": [],
    }
    for creature in creatures:
        seen[species[creature.species_id].diet + "s"].append((creature.x, creature.y))
    return seen


def step_region(
    creatures: list[Creature],
    species: dict[UUID, SpeciesProfile],
    tiles: list[tuple[int, int]],
    vegetation: list[float],
    climate: Climate,
    celsius: float,
    season: str,
    comfort: dict[str, bool],
    rng: random.Random,
) -> StepResult:
    result = StepResult(creatures=[], vegetation=_regrow(vegetation, climate, season))
    started_with = {species[creature.species_id].name for creature in creatures}
    ground = {
        transport: set(allowed_tiles(tiles, transport))
        for transport in {profile.transport for profile in species.values()}
    }
    index_of = {tuple(tile): index for index, tile in enumerate(tiles)}

    living = _endure(creatures, species, celsius, result)
    _move(living, species, ground, index_of, result.vegetation, rng)
    living = _hunt(living, species, result)
    _graze(living, species, index_of, result.vegetation)
    living.extend(_breed(living, species, ground, rng, result))

    result.creatures = living
    remaining = {species[creature.species_id].name for creature in living}
    result.extinct = sorted(started_with - remaining)
    result.comfort = _comfort(remaining, species, celsius, comfort)
    return result


def _regrow(vegetation: list[float], climate: Climate, season: str) -> list[float]:
    rate = REGROWTH[climate.rainfall] * SEASON_GROWTH[season]
    return [min(1.0, value + rate) for value in vegetation]


def _endure(
    creatures: list[Creature],
    species: dict[UUID, SpeciesProfile],
    celsius: float,
    result: StepResult,
) -> list[Creature]:
    living = []

    for creature in creatures:
        profile = species[creature.species_id]
        creature.age += 1
        creature.cooldown = max(0, creature.cooldown - 1)

        too_cold = celsius < profile.min_temperature
        too_hot = celsius > profile.max_temperature
        if too_cold or too_hot:
            creature.stress = min(1.0, creature.stress + STRESS_PER_HOUR)
        else:
            creature.stress = max(0.0, creature.stress - RELIEF_PER_HOUR)

        appetite = STRESSED_APPETITE if creature.stress > 0 else 1.0
        if profile.diet == "carnivore":
            appetite *= CARNIVORE_APPETITE
        creature.hunger = min(1.0, creature.hunger + HUNGER_PER_HOUR * appetite)

        if creature.age >= creature.lifespan:
            result.deaths.append(Death(profile.name, "aged"))
        elif creature.hunger >= 1.0:
            result.deaths.append(Death(profile.name, "starved"))
        elif creature.stress >= 1.0:
            result.deaths.append(
                Death(profile.name, "froze" if too_cold else "scorched")
            )
        else:
            living.append(creature)

    return living


def _neighbours(tile: tuple[int, int]) -> list[tuple[int, int]]:
    x, y = tile
    return [
        (x + dx, y + dy)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        if (dx, dy) != (0, 0)
    ]


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _wander(
    here: tuple[int, int], allowed: set[tuple[int, int]], rng: random.Random
) -> tuple[int, int]:
    options = [tile for tile in _neighbours(here) if tile in allowed]
    return rng.choice(options) if options else here


def _nearest(
    origin: tuple[int, int], options: list[tuple[int, int]], sight: int
) -> tuple[int, int] | None:
    best = None
    closest = sight + 1
    for option in options:
        distance = _distance(origin, option)
        if distance < closest:
            best, closest = option, distance
    return best


def _greenest(
    origin: tuple[int, int], index_of: dict[tuple[int, int], int], vegetation: list[float]
) -> tuple[int, int] | None:
    best = None
    richest = 0.0
    for dx in range(-FORAGE_SIGHT, FORAGE_SIGHT + 1):
        for dy in range(-FORAGE_SIGHT, FORAGE_SIGHT + 1):
            index = index_of.get((origin[0] + dx, origin[1] + dy))
            if index is not None and vegetation[index] > richest:
                best, richest = (origin[0] + dx, origin[1] + dy), vegetation[index]
    return best


def _move(
    creatures: list[Creature],
    species: dict[UUID, SpeciesProfile],
    ground: dict[str, set[tuple[int, int]]],
    index_of: dict[tuple[int, int], int],
    vegetation: list[float],
    rng: random.Random,
) -> None:
    hunters = [c for c in creatures if species[c.species_id].prey]
    grazers = [c for c in creatures if not species[c.species_id].prey]

    for group in (grazers, hunters):
        _advance(group, creatures, species, ground, index_of, vegetation, rng)


def _advance(
    moving: list[Creature],
    everyone: list[Creature],
    species: dict[UUID, SpeciesProfile],
    ground: dict[str, set[tuple[int, int]]],
    index_of: dict[tuple[int, int], int],
    vegetation: list[float],
    rng: random.Random,
) -> None:
    positions: dict[str, list[tuple[int, int]]] = {}
    threats: dict[str, list[tuple[int, int]]] = {}
    for creature in everyone:
        profile = species[creature.species_id]
        positions.setdefault(profile.name, []).append((creature.x, creature.y))
        for name in profile.prey:
            threats.setdefault(name, []).append((creature.x, creature.y))

    for creature in moving:
        profile = species[creature.species_id]
        target, intent = _intent(
            creature, profile, positions, threats, index_of, vegetation
        )
        allowed = ground[profile.transport]
        steps = max(1, round(profile.speed / 2)) + (intent == "chase")
        for _ in range(steps):
            creature.x, creature.y = _stride(creature, target, intent, allowed, rng)


def _intent(
    creature: Creature,
    profile: SpeciesProfile,
    positions: dict[str, list[tuple[int, int]]],
    threats: dict[str, list[tuple[int, int]]],
    index_of: dict[tuple[int, int], int],
    vegetation: list[float],
) -> tuple[tuple[int, int] | None, str]:
    here = (creature.x, creature.y)

    if creature.hunger < FLEE_HUNGER:
        danger = _nearest(here, threats.get(profile.name, []), FLEE_SIGHT)
        if danger:
            return danger, "flee"

    if profile.prey and creature.hunger >= HUNT_HUNGER:
        quarry = _nearest(
            here,
            [tile for name in profile.prey for tile in positions.get(name, [])],
            SIGHT,
        )
        if quarry:
            return quarry, "chase"

    if profile.diet != "carnivore":
        index = index_of.get(here)
        if index is None or vegetation[index] < BARE:
            green = _greenest(here, index_of, vegetation)
            if green and green != here:
                return green, "forage"

    return None, "wander"


def _stride(
    creature: Creature,
    target: tuple[int, int] | None,
    intent: str,
    allowed: set[tuple[int, int]],
    rng: random.Random,
) -> tuple[int, int]:
    here = (creature.x, creature.y)

    if target is None:
        return _wander(here, allowed, rng)

    step = (
        (target[0] > here[0]) - (target[0] < here[0]),
        (target[1] > here[1]) - (target[1] < here[1]),
    )
    if intent == "flee":
        step = (-step[0], -step[1])

    if step == (0, 0):
        return here if intent != "flee" else _wander(here, allowed, rng)

    for candidate in (
        (here[0] + step[0], here[1] + step[1]),
        (here[0] + step[0], here[1]),
        (here[0], here[1] + step[1]),
    ):
        if candidate in allowed:
            return candidate
    return here


def _hunt(
    creatures: list[Creature], species: dict[UUID, SpeciesProfile], result: StepResult
) -> list[Creature]:
    sharing: dict[tuple[int, int], list[Creature]] = {}
    for creature in creatures:
        sharing.setdefault((creature.x, creature.y), []).append(creature)

    eaten: set[UUID] = set()
    hunters = sorted(
        (
            c
            for c in creatures
            if species[c.species_id].prey and c.hunger >= HUNT_HUNGER
        ),
        key=lambda c: -species[c.species_id].speed,
    )

    for hunter in hunters:
        if hunter.id in eaten:
            continue
        profile = species[hunter.species_id]
        here = (hunter.x, hunter.y)
        victim = next(
            (
                other
                for tile in (here, *_neighbours(here))
                for other in sharing.get(tile, ())
                if other.id not in eaten
                and species[other.species_id].name in profile.prey
            ),
            None,
        )
        if victim is None:
            continue
        eaten.add(victim.id)
        hunter.hunger = 0.0
        result.deaths.append(
            Death(species[victim.species_id].name, "killed", profile.name)
        )

    return [creature for creature in creatures if creature.id not in eaten]


def _graze(
    creatures: list[Creature],
    species: dict[UUID, SpeciesProfile],
    index_of: dict[tuple[int, int], int],
    vegetation: list[float],
) -> None:
    for creature in creatures:
        if species[creature.species_id].diet == "carnivore" or creature.hunger == 0:
            continue
        index = index_of.get((creature.x, creature.y))
        if index is None:
            continue
        taken = min(GRAZE_PER_HOUR, vegetation[index], creature.hunger / NOURISHMENT)
        vegetation[index] -= taken
        creature.hunger = max(0.0, creature.hunger - taken * NOURISHMENT)


def _breed(
    creatures: list[Creature],
    species: dict[UUID, SpeciesProfile],
    ground: dict[str, set[tuple[int, int]]],
    rng: random.Random,
    result: StepResult,
) -> list[Creature]:
    ready: dict[UUID, list[Creature]] = {}
    for creature in creatures:
        hunter = species[creature.species_id].diet == "carnivore"
        if (
            creature.cooldown == 0
            and creature.age >= (HUNTER_BREED_AGE if hunter else BREED_AGE)
            and creature.hunger < BREED_HUNGER
            and creature.stress == 0
        ):
            ready.setdefault(creature.species_id, []).append(creature)

    newborns = []
    for species_id, candidates in ready.items():
        profile = species[species_id]
        allowed = ground[profile.transport]
        taken: set[UUID] = set()

        for index, first in enumerate(candidates):
            if first.id in taken:
                continue
            partner = next(
                (
                    other
                    for other in candidates[index + 1 :]
                    if other.id not in taken
                    and _distance((first.x, first.y), (other.x, other.y)) <= 1
                ),
                None,
            )
            if partner is None:
                continue

            taken.update({first.id, partner.id})
            first.cooldown = partner.cooldown = (
                HUNTER_BREED_COOLDOWN if profile.diet == "carnivore" else BREED_COOLDOWN
            )
            spot = next(
                (tile for tile in _neighbours((first.x, first.y)) if tile in allowed),
                (first.x, first.y),
            )
            newborns.append(
                Creature(
                    id=uuid4(),
                    species_id=species_id,
                    x=spot[0],
                    y=spot[1],
                    lifespan=rng.randint(*LIFESPAN),
                )
            )
            result.born.append(profile.name)

    return newborns


def _comfort(
    present: set[str],
    species: dict[UUID, SpeciesProfile],
    celsius: float,
    previous: dict[str, bool],
) -> dict[str, bool]:
    by_name = {profile.name: profile for profile in species.values()}
    changes = {}

    for name in sorted(present):
        profile = by_name[name]
        stressed = (
            celsius < profile.min_temperature or celsius > profile.max_temperature
        )
        if previous.get(name, False) != stressed:
            changes[name] = stressed

    return changes
