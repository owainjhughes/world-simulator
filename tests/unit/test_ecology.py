import random
from uuid import uuid4

from domain.ecology import (
    BREED_AGE,
    OCEAN_TILES,
    Creature,
    Region,
    allowed_tiles,
    carrying_capacity,
    hunting_grounds,
    populate,
    region_suits,
    step_region,
)
from domain.events import Climate, SpeciesProfile
from domain.world import assign_regions


def climate(min_t=-10.0, max_t=20.0, rainfall="moderate", plants=("moss",)):
    return Climate(
        terrain="test",
        min_temperature=min_t,
        max_temperature=max_t,
        rainfall=rainfall,
        plants=list(plants),
    )


def species(
    name="Grazer",
    diet="herbivore",
    min_t=-10.0,
    max_t=20.0,
    food=("moss",),
    prey=(),
    transport="walk",
    speed=2.0,
    home=None,
):
    return SpeciesProfile(
        id=uuid4(),
        name=name,
        region_id=home or uuid4(),
        diet=diet,
        min_temperature=min_t,
        max_temperature=max_t,
        habitat="open ground",
        food=list(food),
        prey=list(prey),
        transport=transport,
        speed=speed,
        migratory=False,
    )


def creature(profile, x=0, y=0, **overrides):
    return Creature(
        id=uuid4(),
        species_id=profile.id,
        x=x,
        y=y,
        lifespan=10_000,
        **overrides,
    )


def step(creatures, profiles, tiles, vegetation, where, celsius, comfort=None, seed=1):
    return step_region(
        creatures,
        {profile.id: profile for profile in profiles},
        tiles,
        vegetation,
        where,
        celsius,
        "summer",
        comfort or {},
        random.Random(seed),
    )


def test_a_species_needs_both_a_tolerable_climate_and_its_food():
    grazer = species(food=["moss"])
    assert region_suits(grazer, climate(plants=["moss"]))
    assert not region_suits(grazer, climate(plants=["thistle"]))
    assert not region_suits(grazer, climate(min_t=30, max_t=50, plants=["moss"]))


def test_a_predator_only_settles_where_its_prey_actually_lives():
    hunter = species(name="Hunter", diet="carnivore", food=[], prey=["Grazer"])
    stocked = Region(uuid4(), climate(), [(0, 0)])
    empty = Region(uuid4(), climate(), [(1, 0)])
    baking = Region(uuid4(), climate(min_t=30, max_t=50), [(2, 0)])
    present = {
        stocked.region_id: {"Grazer"},
        empty.region_id: {"Nibbler"},
        baking.region_id: {"Grazer"},
    }

    grounds = hunting_grounds(hunter, [stocked, empty, baking], present)

    assert [region.region_id for region in grounds] == [stocked.region_id]


def test_spawn_counts_scale_with_how_much_land_there_is():
    small = Region(uuid4(), climate(), [(x, 0) for x in range(60)])
    large = Region(uuid4(), climate(), [(x, 1) for x in range(400)])
    residents = [
        species(name="Small One", home=small.region_id),
        species(name="Large One", home=large.region_id),
    ]

    spawned = populate(random.Random(7), residents, [small, large])

    assert len(spawned[small.region_id]) < len(spawned[large.region_id])


def test_a_dry_region_feeds_fewer_creatures_than_a_wet_one():
    tiles = [(x, 0) for x in range(100)]
    dry = Region(uuid4(), climate(rainfall="arid"), tiles)
    wet = Region(uuid4(), climate(rainfall="torrential"), tiles)

    assert carrying_capacity(dry) < carrying_capacity(wet)


def test_a_species_spawns_somewhere_it_can_live_and_nowhere_it_cannot():
    cold = Region(uuid4(), climate(-40, -10, plants=["lichen"]), [(x, 0) for x in range(60)])
    hot = Region(uuid4(), climate(20, 40, plants=["lichen"]), [(x, 1) for x in range(60)])
    grazer = species(
        min_t=-40, max_t=-8, food=["lichen"], home=cold.region_id
    )

    spawned = populate(random.Random(3), [grazer], [cold, hot])

    assert spawned[cold.region_id]
    assert spawned[hot.region_id] == []


def test_walkers_stay_on_land_but_swimmers_take_to_the_sea():
    tiles = assign_regions()["Kagotsuma"]

    land = allowed_tiles(tiles, "walk")
    water = allowed_tiles(tiles, "swim")

    assert land == [tuple(tile) for tile in tiles]
    assert len(water) > len(land)
    assert set(water) - set(land) <= OCEAN_TILES


def test_vegetation_regrows_faster_where_it_rains_harder():
    grazer = species()
    tiles = [(0, 0)]

    dry = step([], [grazer], tiles, [0.0], climate(rainfall="arid"), 10.0)
    wet = step([], [grazer], tiles, [0.0], climate(rainfall="torrential"), 10.0)

    assert dry.vegetation[0] < wet.vegetation[0]
    assert step([], [grazer], tiles, [1.0], climate(), 10.0).vegetation[0] == 1.0


def test_a_creature_with_nothing_to_eat_starves():
    grazer = species()
    hungry = creature(grazer, hunger=0.99)

    result = step([hungry], [grazer], [(0, 0)], [0.0], climate(), 10.0)

    assert result.creatures == []
    assert [death.cause for death in result.deaths] == ["starved"]


def test_cold_builds_up_until_it_kills_and_warmth_undoes_it():
    grazer = species(min_t=0, max_t=20)
    chilled = creature(grazer, stress=0.99)
    recovering = creature(grazer, stress=0.5)

    killed = step([chilled], [grazer], [(0, 0)], [1.0], climate(), -20.0)
    assert killed.creatures == []
    assert [death.cause for death in killed.deaths] == ["froze"]

    eased = step([recovering], [grazer], [(0, 0)], [1.0], climate(), 10.0)
    assert eased.creatures[0].stress < 0.5


def test_heat_kills_too_and_says_so():
    grazer = species(min_t=0, max_t=20)
    baked = creature(grazer, stress=0.99)

    result = step([baked], [grazer], [(0, 0)], [1.0], climate(), 40.0)

    assert [death.cause for death in result.deaths] == ["scorched"]


def test_a_predator_closes_in_while_its_prey_runs():
    grazer = species(name="Grazer")
    hunter = species(name="Hunter", diet="carnivore", food=[], prey=["Grazer"], speed=2.0)
    tiles = [(x, 0) for x in range(10)]
    chased = creature(grazer, x=2)
    chasing = creature(hunter, x=0)

    result = step([chasing, chased], [grazer, hunter], tiles, [1.0] * 10, climate(), 10.0)

    moved = {c.id: c.x for c in result.creatures}
    assert moved[chasing.id] > 0
    assert moved[chased.id] > 2


def test_sharing_a_tile_with_a_predator_is_fatal():
    grazer = species(name="Grazer")
    hunter = species(name="Hunter", diet="carnivore", food=[], prey=["Grazer"])
    eaten = creature(grazer)
    eating = creature(hunter, hunger=0.6)

    result = step([eating, eaten], [grazer, hunter], [(0, 0)], [1.0], climate(), 10.0)

    assert [c.id for c in result.creatures] == [eating.id]
    assert result.deaths[0].cause == "killed"
    assert result.deaths[0].killed_by == "Hunter"
    assert result.creatures[0].hunger == 0.0


def test_grazing_feeds_the_creature_and_thins_the_tile():
    grazer = species()
    feeding = creature(grazer, hunger=0.5)

    result = step([feeding], [grazer], [(0, 0)], [1.0], climate(), 10.0)

    assert result.creatures[0].hunger == 0.0
    assert result.vegetation[0] < 1.0


def test_a_fed_and_settled_pair_breeds_but_a_lone_creature_does_not():
    grazer = species()
    tiles = [(0, 0), (1, 0)]
    pair = [creature(grazer, x=0, age=BREED_AGE), creature(grazer, x=1, age=BREED_AGE)]

    bred = step(pair, [grazer], tiles, [1.0, 1.0], climate(), 10.0)
    assert bred.born == ["Grazer"]
    assert len(bred.creatures) == 3
    assert all(parent.cooldown > 0 for parent in bred.creatures[:2])

    alone = step(
        [creature(grazer, age=BREED_AGE)], [grazer], tiles, [1.0, 1.0], climate(), 10.0
    )
    assert alone.born == []


def test_a_stressed_pair_does_not_breed():
    grazer = species(min_t=0, max_t=20)
    pair = [
        creature(grazer, x=0, age=BREED_AGE, stress=0.5),
        creature(grazer, x=1, age=BREED_AGE, stress=0.5),
    ]

    result = step(pair, [grazer], [(0, 0), (1, 0)], [1.0, 1.0], climate(), -20.0)

    assert result.born == []


def test_the_last_of_a_species_dying_is_announced():
    grazer = species()
    last = creature(grazer, hunger=0.99)

    result = step([last], [grazer], [(0, 0)], [0.0], climate(), 10.0)

    assert result.extinct == ["Grazer"]


def test_comfort_is_reported_only_when_it_changes():
    grazer = species(min_t=0, max_t=20)
    living = creature(grazer)

    stressed = step([living], [grazer], [(0, 0)], [1.0], climate(), 30.0)
    assert stressed.comfort == {"Grazer": True}

    still = step([living], [grazer], [(0, 0)], [1.0], climate(), 30.0, {"Grazer": True})
    assert still.comfort == {}

    eased = step([living], [grazer], [(0, 0)], [1.0], climate(), 10.0, {"Grazer": True})
    assert eased.comfort == {"Grazer": False}


def test_a_herbivore_leaves_a_bare_tile_for_a_greener_one():
    grazer = species()
    tiles = [(0, 0), (1, 0), (2, 0)]
    standing = creature(grazer, x=0)

    result = step([standing], [grazer], tiles, [0.0, 0.0, 1.0], climate(), 10.0)

    assert result.creatures[0].x > 0
