import asyncio
import io
import sys

import app.viewer.main as viewer


def build_world(width=6, height=4):
    viewer.log.clear()
    viewer.screen["frame"] = None
    viewer.screen["tick"] = 0
    viewer.now = {"day": 0, "hour": 0, "season": "winter", "night": False}
    viewer.world["id"] = "w1"
    viewer.world["grid"] = [["#00AFAF"] * width for _ in range(height)]
    viewer.world["owners"] = [[None] * width for _ in range(height)]
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


def own_row(y):
    width = len(viewer.world["owners"][y])
    viewer.world["owners"][y] = ["wyldvale"] * width


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
    assert viewer.now == {"day": 3, "hour": 6, "season": "spring", "night": False}


def test_events_from_other_worlds_are_dropped():
    build_world()
    viewer.apply_event("clock.temperature.changed.wyldvale", temperature_payload("w2"))
    assert viewer.world["regions"]["wyldvale"]["celsius"] == 12.5
    assert viewer.now == {"day": 0, "hour": 0, "season": "winter", "night": False}


def weather_payload(world_id, condition="rain"):
    return {"world_id": world_id, "region_slug": "wyldvale", "condition": condition}


def test_weather_starting_appends_to_the_log():
    build_world()
    viewer.apply_event("clock.weather.rain.started.wyldvale", weather_payload("w1"))
    assert list(viewer.log) == ["day 0 00:00  rain started in Wyldvale"]


def test_weather_stopping_appends_to_the_log():
    build_world()
    viewer.apply_event("clock.weather.rain.stopped.wyldvale", weather_payload("w1"))
    assert list(viewer.log) == ["day 0 00:00  rain stopped in Wyldvale"]


def test_season_changes_append_to_the_log():
    build_world()
    viewer.apply_event("clock.season.changed", {"world_id": "w1", "season": "spring"})
    assert list(viewer.log) == ["day 0 00:00  season changed to spring"]


def test_temperature_changes_stay_out_of_the_log():
    build_world()
    viewer.apply_event("clock.temperature.changed.wyldvale", temperature_payload("w1"))
    assert not viewer.log


def test_the_log_keeps_only_the_last_ten_entries():
    build_world()
    for _ in range(12):
        viewer.apply_event("clock.weather.rain.started.wyldvale", weather_payload("w1"))
    assert len(viewer.log) == 10


def test_the_legend_lays_continents_out_in_columns():
    build_world()
    viewer.world["order"] = ["wyldvale", "chillcap"]
    viewer.world["regions"]["chillcap"] = {
        "name": "Chillcap",
        "continent": "Northsaw",
        "latitude": 2.0,
        "colour": "#1D46B4",
        "celsius": None,
        "weather": set(),
    }
    lines = viewer.legend_lines()
    assert any("Chillcap" in line and "Wyldvale" in line for line in lines)


def test_the_log_renders_beside_the_legend_below_the_map():
    build_world(width=6, height=4)
    viewer.apply_event("clock.weather.rain.started.wyldvale", weather_payload("w1"))
    lines = render_to_string().split("\n")
    map_rows = [i for i, line in enumerate(lines) if line.count("48;2;") == 6]
    title_row = next(i for i, line in enumerate(lines) if "World log" in line)
    entry_row = next(i for i, line in enumerate(lines) if "rain started in Wyldvale" in line)
    assert len(map_rows) == 4
    assert max(map_rows) < title_row
    assert "Kuerigo" in lines[title_row]
    assert "Wyldvale" in lines[entry_row]


def test_identical_frames_are_not_rewritten():
    build_world()
    first = render_to_string()
    second = render_to_string()
    assert first
    assert second == ""


def test_frames_are_wrapped_in_synchronized_update_escapes():
    build_world()
    body = render_to_string()
    assert body.startswith("\x1b[?2026h")
    assert body.endswith("\x1b[?2026l")


def test_the_quit_key_shows_beside_the_log_title():
    build_world()
    lines = render_to_string().split("\n")
    title = next(line for line in lines if "World log" in line)
    assert "[q] menu" in title
    assert "[q] menu" not in lines[0]


def test_watching_keys_ends_on_q(monkeypatch):
    keys = iter(["x", "q"])
    monkeypatch.setattr(viewer, "read_key", lambda: next(keys))
    asyncio.run(viewer.watch_keys())


def test_night_dims_map_tiles_but_not_legend_swatches():
    build_world()
    viewer.now["night"] = True
    body = render_to_string()
    assert "48;2;0;96;96" in body
    assert "48;2;95;0;175" in body
    assert "48;2;0;175;175" not in body


def test_day_and_night_events_flip_the_night_flag():
    build_world()
    viewer.apply_event("clock.night.arrived", {"world_id": "w1", "day": 0})
    assert viewer.now["night"]
    viewer.apply_event("clock.day.arrived", {"world_id": "w1", "day": 1})
    assert not viewer.now["night"]


def test_sunshine_brightens_region_tiles_without_glyphs():
    build_world()
    own_row(0)
    viewer.world["regions"]["wyldvale"]["weather"] = {"sunshine"}
    body = render_to_string()
    assert "48;2;0;218;218" in body
    assert "\x1b[97m" not in body


def test_brightening_clamps_at_white():
    build_world()
    own_row(0)
    viewer.world["grid"][0] = ["#FFCC00"] * 6
    viewer.world["regions"]["wyldvale"]["weather"] = {"sunshine"}
    body = render_to_string()
    assert "48;2;255;255;0" in body


def test_rain_marks_one_tile_in_five():
    build_world(width=10)
    own_row(0)
    body = render_to_string()
    assert body.count("\x1b[97m/ ") == 2


def test_rain_falls_one_row_per_frame():
    build_world()
    own_row(1)
    own_row(2)

    def map_rows(body):
        return [line for line in body.split("\n") if line.count("48;2;") == 6]

    first = map_rows(render_to_string())
    viewer.screen["frame"] = None
    viewer.screen["tick"] = 1
    second = map_rows(render_to_string())
    assert second[2] == first[1]


def test_snow_floats_at_half_speed():
    build_world()
    own_row(0)
    viewer.world["regions"]["wyldvale"]["weather"] = {"snow"}
    assert render_to_string()
    viewer.screen["tick"] = 1
    assert render_to_string() == ""
    viewer.screen["tick"] = 2
    assert render_to_string()


def test_snow_outranks_wind():
    build_world()
    own_row(0)
    viewer.world["regions"]["wyldvale"]["weather"] = {"snow", "wind"}
    body = render_to_string()
    assert "*" in body
    assert "~" not in body


def test_map_tiles_paint_two_characters_wide():
    build_world(width=6, height=4)
    viewer.world["order"] = []
    viewer.world["regions"] = {}
    body = render_to_string()
    drawn = [line for line in body.split("\n") if "48;2;" in line]
    assert drawn
    assert all("m  \x1b" in line for line in drawn)
