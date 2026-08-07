import app.viewer.menu as menu

WORLDS = [
    {"id": "aaaa1111-0000-0000-0000-000000000000", "seed": 42},
    {"id": "bbbb2222-0000-0000-0000-000000000000", "seed": 7},
]


def test_pick_returns_the_numbered_world():
    assert menu.pick(WORLDS, "2") is WORLDS[1]


def test_pick_rejects_junk_and_out_of_range():
    assert menu.pick(WORLDS, "") is None
    assert menu.pick(WORLDS, "nope") is None
    assert menu.pick(WORLDS, "3") is None


def test_show_marks_running_and_idle_worlds(capsys):
    running = {WORLDS[0]["id"]: {"day": 12, "hour": 6, "season": "spring"}}
    menu.show(WORLDS, running)
    output = capsys.readouterr().out
    assert "day  12 06:00 spring" in output
    assert "idle" in output
    assert "aaaa1111" in output and "bbbb2222" in output
