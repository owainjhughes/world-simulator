import math
import random

SEASONS = ("winter", "spring", "summer", "autumn")
DAYS_PER_SEASON = 30
DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)
HOURS_PER_DAY = 24
DAWN_HOUR = 6
DUSK_HOUR = 18


def season_for_day(day: int) -> str:
    return SEASONS[(day // DAYS_PER_SEASON) % len(SEASONS)]


def is_daytime(hour: int) -> bool:
    return DAWN_HOUR <= hour < DUSK_HOUR


def temperature(climate: dict, day: int, hour: int, rng: random.Random) -> float:
    span = climate["max_temperature"] - climate["min_temperature"]
    seasonal = (1 - math.cos(2 * math.pi * (day % DAYS_PER_YEAR) / DAYS_PER_YEAR)) / 2
    daily = (1 - math.cos(2 * math.pi * (hour - 4) / HOURS_PER_DAY)) / 2
    reading = (
        climate["min_temperature"]
        + span * (0.65 * seasonal + 0.35 * daily)
        + rng.uniform(-1, 1)
    )
    return round(reading, 1)
