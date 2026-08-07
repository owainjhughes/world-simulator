import io
import sys

import app.viewer.main as viewer


def build_world(width=6, height=4):
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
