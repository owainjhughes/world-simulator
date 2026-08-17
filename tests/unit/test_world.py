from domain.atlas import CONTINENTS, HEIGHT, MAP_ROWS, OCEAN, REGIONS, WIDTH
from domain.world import generate_world


def test_no_tile_belongs_to_two_regions():
    _, regions, _ = generate_world(seed=1)
    tiles = [tuple(tile) for region in regions for tile in region.tiles]
    assert len(tiles) == len(set(tiles))


def test_the_world_has_both_land_and_sea():
    _, regions, _ = generate_world(seed=1)
    land = sum(len(region.tiles) for region in regions)
    assert 0 < land < WIDTH * HEIGHT
    assert land < WIDTH * HEIGHT * 0.6


def test_all_named_regions_are_present_and_populated():
    _, regions, species_events = generate_world(seed=2)
    assert [region.name for region in regions] == [name for _, name, _, _, _ in REGIONS]
    assert all(region.tiles for region in regions)
    assert all(event.species for event in species_events)


def test_every_painted_tile_is_claimed_by_a_region():
    _, regions, _ = generate_world(seed=1)
    claimed = sum(len(region.tiles) for region in regions)
    painted = sum(len(row) - row.count(OCEAN) for row in MAP_ROWS)
    assert claimed == painted


def test_islands_stay_small():
    _, regions, _ = generate_world(seed=1)
    by_name = {region.name: region.tiles for region in regions}
    assert len(by_name["Kagotsuma"]) < len(by_name["Denn Arctogh"])
    assert len(by_name["Doreidrassil"]) < len(by_name["Denn Arctogh"])


def test_regions_carry_a_colour():
    _, regions, _ = generate_world(seed=1)
    for region in regions:
        assert region.colour.startswith("#")
        assert len(region.colour) == 7


def test_every_region_belongs_to_a_named_continent():
    _, regions, _ = generate_world(seed=1)
    assert {region.continent for region in regions} == set(CONTINENTS)


def test_islands_are_grouped_with_their_nearest_continent():
    _, regions, _ = generate_world(seed=1)
    continent_of = {region.name: region.continent for region in regions}
    assert continent_of["Doreidrassil"] == continent_of["Trynwyn"]
    assert continent_of["Kagotsuma"] == continent_of["Wylenn"]


def test_the_same_seed_rebuilds_the_same_world():
    _, first, _ = generate_world(seed=99)
    _, second, _ = generate_world(seed=99)
    assert [region.tiles for region in first] == [region.tiles for region in second]


def test_the_map_is_the_same_whatever_the_seed():
    _, first, _ = generate_world(seed=1)
    _, second, _ = generate_world(seed=2)
    assert [region.tiles for region in first] == [region.tiles for region in second]


def test_the_map_is_a_clean_rectangle():
    assert len(MAP_ROWS) == HEIGHT
    assert {len(row) for row in MAP_ROWS} == {WIDTH}


def test_species_names_are_unique_across_the_world():
    _, _, species_events = generate_world(seed=3)
    names = [profile.name for event in species_events for profile in event.species]
    assert len(names) == len(set(names))


def test_predators_only_hunt_non_carnivores_they_could_actually_meet():
    _, _, species_events = generate_world(seed=4)
    everything = {
        profile.name: profile for event in species_events for profile in event.species
    }
    for profile in everything.values():
        for name in profile.prey:
            prey = everything[name]
            assert name != profile.name
            assert prey.diet != "carnivore"
            assert prey.min_temperature <= profile.max_temperature
            assert profile.min_temperature <= prey.max_temperature


def test_herbivores_eat_plants_and_hunt_nothing():
    _, _, species_events = generate_world(seed=5)
    for event in species_events:
        for profile in event.species:
            if profile.diet == "herbivore":
                assert profile.prey == []
                assert profile.food
            if profile.diet == "carnivore":
                assert profile.food == []


def test_species_only_eat_plants_that_grow_where_they_were_born():
    _, regions, species_events = generate_world(seed=7)
    plants_of = {region.region_id: region.climate.plants for region in regions}
    for event in species_events:
        for profile in event.species:
            assert set(profile.food) <= set(plants_of[event.region_id])


def test_every_region_grows_something():
    _, regions, _ = generate_world(seed=8)
    assert all(region.climate.plants for region in regions)


def test_temperature_preferences_are_the_right_way_round():
    _, _, species_events = generate_world(seed=6)
    for event in species_events:
        for profile in event.species:
            assert profile.min_temperature < profile.max_temperature
