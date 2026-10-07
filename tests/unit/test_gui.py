import os

import pytest

pygame = pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from test_viewer import build_world, own_row  # noqa: E402

import app.viewer.gui as gui  # noqa: E402
import app.viewer.main as terminal  # noqa: E402


@pytest.fixture
def screen():
    pygame.display.init()
    pygame.font.init()
    yield pygame.display.set_mode((400, 300 + gui.PANEL))
    pygame.quit()


def test_a_frame_draws_the_world_and_its_creatures(screen):
    build_world(width=6, height=4)
    own_row(1)
    terminal.world["regions"]["wyldvale"]["weather"] = {"rain", "snow", "wind", "sunshine"}
    gui.herd.sprites.clear()
    sightings = [
        {"id": "a", "species": "Mossback", "diet": "herbivore", "transport": "walk", "x": 1, "y": 1},
        {"id": "b", "species": "Gloomwing", "diet": "carnivore", "transport": "fly", "x": 3, "y": 1},
    ]
    gui.apply_event(
        "ecology.census.wyldvale",
        {"world_id": "w1", "region_slug": "wyldvale", "creatures": sightings},
        at=0.0,
    )
    assert set(gui.herd.sprites) == {"a", "b"}

    view = gui.View(*screen.get_size())
    gui.Painter().draw(screen, view, 1.0, (0, 0))
    with_creatures = pygame.image.tobytes(screen, "RGB")
    gui.herd.sprites.clear()
    gui.Painter().draw(screen, view, 1.0, (0, 0))
    assert pygame.image.tobytes(screen, "RGB") != with_creatures


def test_a_census_for_another_world_is_ignored():
    build_world()
    gui.herd.sprites.clear()
    gui.apply_event(
        "ecology.census.wyldvale",
        {"world_id": "other", "region_slug": "wyldvale", "creatures": [
            {"id": "a", "species": "M", "diet": "herbivore", "transport": "walk", "x": 0, "y": 0}
        ]},
        at=0.0,
    )
    assert gui.herd.sprites == {}
