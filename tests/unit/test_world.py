from domain.world import HEIGHT, REGIONS, WIDTH, generate_world


def test_every_tile_belongs_to_exactly_one_region():
    _, regions, _ = generate_world(seed=1)
    tiles = [tuple(tile) for region in regions for tile in region.tiles]
    assert len(tiles) == WIDTH * HEIGHT
    assert len(set(tiles)) == WIDTH * HEIGHT


def test_all_named_regions_are_present_and_populated():
    _, regions, species_events = generate_world(seed=2)
    assert [region.name for region in regions] == [name for name, _, _ in REGIONS]
    assert all(region.tiles for region in regions)
    assert all(event.species for event in species_events)


def test_the_same_seed_rebuilds_the_same_world():
    _, first, _ = generate_world(seed=99)
    _, second, _ = generate_world(seed=99)
    assert [region.tiles for region in first] == [region.tiles for region in second]


def test_different_seeds_move_the_borders():
    _, first, _ = generate_world(seed=1)
    _, second, _ = generate_world(seed=2)
    assert [region.tiles for region in first] != [region.tiles for region in second]


def test_species_names_are_unique_across_the_world():
    _, _, species_events = generate_world(seed=3)
    names = [profile.name for event in species_events for profile in event.species]
    assert len(names) == len(set(names))


def test_predators_only_hunt_non_carnivores_in_their_own_region():
    _, _, species_events = generate_world(seed=4)
    for event in species_events:
        local = {profile.name: profile for profile in event.species}
        for profile in event.species:
            for prey in profile.prey:
                assert prey in local
                assert prey != profile.name
                assert local[prey].diet != "carnivore"


def test_herbivores_eat_plants_and_hunt_nothing():
    _, _, species_events = generate_world(seed=5)
    for event in species_events:
        for profile in event.species:
            if profile.diet == "herbivore":
                assert profile.prey == []
                assert profile.food
            if profile.diet == "carnivore":
                assert profile.food == []


def test_temperature_preferences_are_the_right_way_round():
    _, _, species_events = generate_world(seed=6)
    for event in species_events:
        for profile in event.species:
            assert profile.min_temperature < profile.max_temperature
