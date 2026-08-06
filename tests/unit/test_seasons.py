import random

from domain.seasons import DAYS_PER_SEASON, DAYS_PER_YEAR, season_for_day, temperature

CLIMATE = {
    "terrain": "forest",
    "min_temperature": 2.0,
    "max_temperature": 20.0,
    "rainfall": "moderate",
}


def test_year_starts_in_winter_and_cycles():
    assert season_for_day(0) == "winter"
    assert season_for_day(DAYS_PER_SEASON) == "spring"
    assert season_for_day(DAYS_PER_SEASON * 2) == "summer"
    assert season_for_day(DAYS_PER_SEASON * 3) == "autumn"
    assert season_for_day(DAYS_PER_YEAR) == "winter"


def test_season_holds_for_its_whole_length():
    assert {season_for_day(day) for day in range(DAYS_PER_SEASON)} == {"winter"}


def test_temperature_stays_near_the_climate_band():
    rng = random.Random(1)
    readings = [
        temperature(CLIMATE, day, hour, rng)
        for day in range(DAYS_PER_YEAR)
        for hour in range(24)
    ]
    assert min(readings) >= CLIMATE["min_temperature"] - 1.5
    assert max(readings) <= CLIMATE["max_temperature"] + 1.5


def test_midsummer_afternoon_beats_midwinter_night():
    rng = random.Random(1)
    midwinter_night = temperature(CLIMATE, 0, 4, rng)
    midsummer_afternoon = temperature(CLIMATE, DAYS_PER_YEAR // 2, 16, rng)
    assert midsummer_afternoon > midwinter_night
