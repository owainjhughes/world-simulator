from app.viewer.herd import FADE_SECONDS, SHAPES, Herd, look_for, pixels


def sighting(creature_id, x, y, species="Mossback", diet="herbivore", transport="walk"):
    return {
        "id": creature_id,
        "species": species,
        "diet": diet,
        "transport": transport,
        "x": x,
        "y": y,
    }


def test_a_species_always_looks_the_same():
    assert look_for("Mossback", "herbivore", "walk") == look_for(
        "Mossback", "herbivore", "walk"
    )


def test_species_shape_follows_how_they_move():
    for transport, shapes in SHAPES.items():
        assert list(look_for("Glimmerfin", "omnivore", transport).rows) in shapes


def test_carnivores_have_red_eyes():
    look = look_for("Ember Stalker", "carnivore", "walk")
    assert (230, 30, 30) in {colour for _, _, colour in pixels(look, 0)}


def test_animation_frames_differ():
    look = look_for("Sky Warbler", "herbivore", "fly")
    assert pixels(look, 0) != pixels(look, 1)


def test_a_new_creature_appears_where_it_was_seen():
    herd = Herd()
    herd.observe("wyldvale", [sighting("a", 3, 4)], at=0.0)
    x, y = herd.sprites["a"].place(0.0)
    assert 3 <= x < 4 and 4 <= y < 5


def test_a_creature_glides_to_its_next_tile_over_the_tick():
    herd = Herd()
    herd.observe("wyldvale", [sighting("a", 0, 0)], at=0.0)
    herd.observe("wyldvale", [sighting("a", 4, 0)], at=2.0)
    start = herd.sprites["a"].place(2.0)[0]
    middle = herd.sprites["a"].place(3.0)[0]
    end = herd.sprites["a"].place(4.0)[0]
    assert start < middle < end
    assert 4 <= end < 5
    assert herd.sprites["a"].facing == 1


def test_a_creature_facing_flips_when_it_turns_back():
    herd = Herd()
    herd.observe("wyldvale", [sighting("a", 5, 0)], at=0.0)
    herd.observe("wyldvale", [sighting("a", 1, 0)], at=2.0)
    assert herd.sprites["a"].facing == -1


def test_a_creature_missing_from_its_census_fades_away():
    herd = Herd()
    herd.observe("wyldvale", [sighting("a", 0, 0), sighting("b", 1, 1)], at=0.0)
    herd.observe("wyldvale", [sighting("b", 1, 1)], at=2.0)
    assert herd.sprites["a"].opacity(2.0 + FADE_SECONDS / 2) < 1
    assert {sprite.id for sprite in herd.visible(2.0 + FADE_SECONDS)} == {"b"}


def test_a_census_only_touches_its_own_region():
    herd = Herd()
    herd.observe("wyldvale", [sighting("a", 0, 0)], at=0.0)
    herd.observe("chillcap", [sighting("b", 9, 9)], at=1.0)
    assert herd.sprites["a"].died_at is None


def test_nearest_finds_the_creature_under_the_cursor():
    herd = Herd()
    herd.observe("wyldvale", [sighting("a", 0, 0), sighting("b", 6, 6)], at=0.0)
    assert herd.nearest(6.5, 6.5, at=0.0).id == "b"
    assert herd.nearest(3.0, 3.0, at=0.0) is None
