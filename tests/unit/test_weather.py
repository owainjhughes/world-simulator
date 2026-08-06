import random

from domain.weather import update_weather

WET = {
    "terrain": "jungle",
    "min_temperature": 20.0,
    "max_temperature": 38.0,
    "rainfall": "torrential",
}
DRY = {
    "terrain": "desert",
    "min_temperature": 8.0,
    "max_temperature": 46.0,
    "rainfall": "arid",
}


def _run_until_precipitation(climate, celsius, seed_limit=200):
    for seed in range(seed_limit):
        active, started, _ = update_weather([], climate, celsius, random.Random(seed))
        precipitation = {"rain", "snow"} & set(started)
        if precipitation:
            return precipitation.pop()
    raise AssertionError("no precipitation in any seeded run")


def test_below_freezing_gives_snow_not_rain():
    assert _run_until_precipitation(WET, -5.0) == "snow"


def test_above_freezing_gives_rain_not_snow():
    assert _run_until_precipitation(WET, 12.0) == "rain"


def test_rain_and_snow_never_fall_together():
    rng = random.Random(7)
    active = ["rain"]
    for _ in range(500):
        active, _, _ = update_weather(active, WET, -5.0, rng)
        assert not {"rain", "snow"}.issubset(set(active))


def test_arid_regions_stay_drier_than_torrential_ones():
    def wet_ticks(climate):
        rng = random.Random(3)
        active, count = [], 0
        for _ in range(2000):
            active, _, _ = update_weather(active, climate, 15.0, rng)
            if "rain" in active:
                count += 1
        return count

    assert wet_ticks(DRY) < wet_ticks(WET)


def test_stopping_reports_what_was_active():
    rng = random.Random(0)
    active, started, stopped = update_weather(["rain"], WET, 15.0, rng)
    for condition in stopped:
        assert condition not in active
