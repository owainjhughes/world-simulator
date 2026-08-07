import io
import sys

import app.viewer.main as viewer


def build_world(width=6, height=4):
    viewer.now = {"day": 0, "hour": 0, "season": "winter"}
    viewer.world["id"] = "w1"
    viewer.world["grid"] = [["#00AFAF"] * width for _ in range(height)]
    viewer.world["order"] = ["wyldvale"]
    viewer.world["regions"] = {
        "wyldvale": {
            "name": "Wyldvale",
            "continent": "Kuerigo",
            "latitude": 1.0,
            "colour": "#5F00AF",
            "celsius": 12.5,
            "weather": {"rain"},
        }
    }


def render_to_string() -> str:
    buffer = io.StringIO()
    real, sys.stdout = sys.stdout, buffer
    try:
        viewer.render()
    finally:
        sys.stdout = real
    return buffer.getvalue()


def test_the_legend_paints_a_swatch_for_every_region():
    build_world()
    lines = viewer.legend_lines()
    assert any("Wyldvale" in line for line in lines)
    assert any("12.5C" in line for line in lines)


def test_the_map_draws_one_line_per_row():
    build_world(width=6, height=4)
    viewer.world["order"] = []
    viewer.world["regions"] = {}
    body = render_to_string()
    drawn = [line for line in body.split("\n") if "48;2;" in line]
    assert len(drawn) == 4
    assert all(line.count("48;2;") == 6 for line in drawn)


def temperature_payload(world_id):
    return {
        "world_id": world_id,
        "region_slug": "wyldvale",
        "celsius": 20.0,
        "day": 3,
        "hour": 6,
        "season": "spring",
    }


def test_events_for_the_watched_world_apply():
    build_world()
    viewer.apply_event("clock.temperature.changed.wyldvale", temperature_payload("w1"))
    assert viewer.world["regions"]["wyldvale"]["celsius"] == 20.0
    assert viewer.now == {"day": 3, "hour": 6, "season": "spring"}


def test_events_from_other_worlds_are_dropped():
    build_world()
    viewer.apply_event("clock.temperature.changed.wyldvale", temperature_payload("w2"))
    assert viewer.world["regions"]["wyldvale"]["celsius"] == 12.5
    assert viewer.now == {"day": 0, "hour": 0, "season": "winter"}
