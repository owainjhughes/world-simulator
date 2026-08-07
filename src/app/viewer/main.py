import asyncio
import json
import os
import sys
from collections import deque

import aio_pika
import httpx

from domain.atlas import CONTINENTS, OCEAN_COLOUR

GENESIS_URL = os.environ.get("GENESIS_URL", "http://localhost:18800")
AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost:18801/")
WORLD_ID = os.environ.get("WORLD_ID")
REFRESH_SECONDS = 0.5
RESET = "\x1b[0m"
COLUMN = 33

world = {"id": None, "grid": [], "regions": {}, "order": []}
now = {"day": 0, "hour": 0, "season": "winter"}
log = deque(maxlen=10)
screen = {"frame": None}


def paint(colour: str, width: int = 1) -> str:
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return f"\x1b[48;2;{red};{green};{blue}m{' ' * width}\x1b[49m"


async def load_world() -> None:
    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=10) as client:
        worlds = (await client.get("/worlds")).json()
        if not worlds:
            sys.exit(f"no world yet - create one with: curl -X POST {GENESIS_URL}/worlds")
        chosen = next(w for w in worlds if w["id"] == WORLD_ID) if WORLD_ID else worlds[-1]
        regions = (await client.get(f"/worlds/{chosen['id']}/regions")).json()

    world["id"] = chosen["id"]
    world["grid"] = [[OCEAN_COLOUR] * chosen["width"] for _ in range(chosen["height"])]

    for region in regions:
        colour = region["colour"]
        world["order"].append(region["slug"])
        world["regions"][region["slug"]] = {
            "name": region["name"],
            "continent": region["continent"],
            "latitude": sum(y for _, y in region["tiles"]) / len(region["tiles"]),
            "colour": colour,
            "celsius": None,
            "weather": set(),
        }
        for x, y in region["tiles"]:
            world["grid"][y][x] = colour


def cell(colour: str | None, text: str) -> str:
    swatch = paint(colour) if colour else " "
    return swatch + f" {text}"[: COLUMN - 1].ljust(COLUMN - 1)


def continent_cells(continent: str) -> list[str]:
    members = [
        slug
        for slug in world["order"]
        if world["regions"][slug]["continent"] == continent
    ]
    if not members:
        return []
    members.sort(key=lambda slug: world["regions"][slug]["latitude"])
    cells = [cell(None, continent)]
    for slug in members:
        region = world["regions"][slug]
        celsius = (
            "     -" if region["celsius"] is None else f"{region['celsius']:5.1f}C"
        )
        weather = " ".join(sorted(region["weather"]))
        cells.append(cell(region["colour"], f"{region['name']:<16}{celsius} {weather}"))
    return cells


def legend_lines() -> list[str]:
    columns = [cells for continent in CONTINENTS if (cells := continent_cells(continent))]
    if not columns:
        return []
    height = max(len(column) for column in columns)
    for column in columns:
        column.extend([" " * COLUMN] * (height - len(column)))
    return ["  " + "".join(row) for row in zip(*columns)]


def lower_lines() -> list[str]:
    legend = legend_lines()
    events = ["  World log   [q] menu", *(f"  {entry}" for entry in log)]
    height = max(len(legend), len(events))
    legend.extend([" " * (2 + 3 * COLUMN)] * (height - len(legend)))
    events.extend([""] * (height - len(events)))
    return [left + right for left, right in zip(legend, events)]


def render() -> None:
    lines = [f"  Arathia   day {now['day']}  {now['hour']:02d}:00  {now['season']}", ""]
    lines.extend(
        "  " + "".join(paint(colour, 2) for colour in row) for row in world["grid"]
    )
    lines.append("")
    lines.extend(lower_lines())

    body = "\x1b[K\n".join(lines)
    if body == screen["frame"]:
        return
    screen["frame"] = body
    sys.stdout.write("\x1b[?2026h\x1b[?25l\x1b[H" + body + "\x1b[K\n\x1b[0J\x1b[?2026l")
    sys.stdout.flush()


def apply_event(routing_key: str, payload: dict) -> None:
    if payload["world_id"] != world["id"]:
        return
    slug = payload.get("region_slug")
    region = world["regions"].get(slug) if slug else None

    if routing_key.startswith("clock.temperature.changed"):
        if region:
            region["celsius"] = payload["celsius"]
        now["day"] = payload["day"]
        now["hour"] = payload["hour"]
        now["season"] = payload["season"]
    elif routing_key.startswith("clock.weather.") and region:
        stamp = f"day {now['day']} {now['hour']:02d}:00"
        if routing_key.endswith(f".started.{slug}"):
            region["weather"].add(payload["condition"])
            log.append(f"{stamp}  {payload['condition']} started in {region['name']}")
        else:
            region["weather"].discard(payload["condition"])
            log.append(f"{stamp}  {payload['condition']} stopped in {region['name']}")
    elif routing_key == "clock.season.changed":
        now["season"] = payload["season"]
        log.append(
            f"day {now['day']} {now['hour']:02d}:00  season changed to {payload['season']}"
        )


async def consume() -> None:
    connection = await aio_pika.connect_robust(AMQP_URL)
    channel = await connection.channel()
    exchange = await channel.declare_exchange(
        "world.events", aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(exclusive=True)
    await queue.bind(exchange, routing_key="clock.#")

    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():
                apply_event(message.routing_key, json.loads(message.body))


async def redraw() -> None:
    while True:
        render()
        await asyncio.sleep(REFRESH_SECONDS)


def read_key() -> str:
    if sys.platform == "win32":
        import msvcrt

        return msvcrt.getch().decode(errors="ignore").lower()
    return sys.stdin.read(1).lower()


async def watch_keys() -> None:
    loop = asyncio.get_running_loop()
    while await loop.run_in_executor(None, read_key) != "q":
        pass


async def main() -> None:
    if sys.platform == "win32":
        os.system("")
    await load_world()
    sys.stdout.write("\x1b[?1049h")
    tasks = [asyncio.create_task(work) for work in (consume(), redraw())]
    await watch_keys()
    for task in tasks:
        task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[?1049l" + RESET + "\x1b[?25h")
