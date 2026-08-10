import random

RAINFALL_CHANCE = {
    "arid": 0.02,
    "low": 0.05,
    "moderate": 0.10,
    "high": 0.18,
    "torrential": 0.30,
}

STOP_PRECIPITATION_CHANCE = 0.25
AMBIENT_CHANCES = (("sunshine", 0.15, 0.20), ("wind", 0.12, 0.25))


def update_weather(
    active: list[str], climate: dict, celsius: float, rng: random.Random, is_day: bool
) -> tuple[list[str], list[str], list[str]]:
    current = set(active)
    started: list[str] = []
    stopped: list[str] = []

    precipitation = current & {"rain", "snow"}
    if precipitation:
        if rng.random() < STOP_PRECIPITATION_CHANCE:
            condition = precipitation.pop()
            current.discard(condition)
            stopped.append(condition)
    elif rng.random() < RAINFALL_CHANCE[climate["rainfall"]]:
        condition = "snow" if celsius < 0 else "rain"
        current.add(condition)
        started.append(condition)

    for condition, start_chance, stop_chance in AMBIENT_CHANCES:
        if condition == "sunshine" and not is_day:
            if "sunshine" in current:
                current.discard("sunshine")
                stopped.append("sunshine")
            continue
        if condition in current:
            if rng.random() < stop_chance:
                current.discard(condition)
                stopped.append(condition)
        elif rng.random() < start_chance:
            current.add(condition)
            started.append(condition)

    return sorted(current), started, stopped
