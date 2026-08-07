import asyncio
import json
import os
import sys

import aio_pika
import httpx

from domain.atlas import CONTINENTS, OCEAN_COLOUR

GENESIS_URL = os.environ.get("GENESIS_URL", "http://localhost:8000")
AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost/")
WORLD_ID = os.environ.get("WORLD_ID")
REFRESH_SECONDS = 0.5
RESET = "\x1b[0m"

world = {"id": None, "grid": [], "regions": {}, "order": []}
now = {"day": 0, "hour": 0, "season": "winter"}


def paint(colour: str) -> str:
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return f"\x1b[48;2;{red};{green};{blue}m \x1b[49m"


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


def legend_lines() -> list[str]:
    lines = []

    for continent in CONTINENTS:
        members = [
            slug
            for slug in world["order"]
            if world["regions"][slug]["continent"] == continent
        ]
        if not members:
            continue

        members.sort(key=lambda slug: world["regions"][slug]["latitude"])
        lines.append(f"  {continent}")
        for slug in members:
            region = world["regions"][slug]
            celsius = (
                "      -" if region["celsius"] is None else f"{region['celsius']:6.1f}C"
            )
            weather = " ".join(sorted(region["weather"]))
            lines.append(
                f"  {paint(region['colour'])}{RESET} {region['name']:<16}"
                f"{celsius}  {weather}"
            )
        lines.append("")

    return lines


def render() -> None:
    lines = [f"  Arathia   day {now['day']}  {now['hour']:02d}:00  {now['season']}", ""]
    legend = legend_lines()

    for y, row in enumerate(world["grid"]):
        side = f"   {legend[y]}" if y < len(legend) else ""
        lines.append("  " + "".join(paint(colour) for colour in row) + side)

    body = "\x1b[K\n".join(lines)
    sys.stdout.write("\x1b[?25l\x1b[H" + body + "\x1b[K\n\x1b[0J")
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
        if routing_key.endswith(f".started.{slug}"):
            region["weather"].add(payload["condition"])
        else:
            region["weather"].discard(payload["condition"])
    elif routing_key == "clock.season.changed":
        now["season"] = payload["season"]


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


async def main() -> None:
    if sys.platform == "win32":
        os.system("")
    await load_world()
    await asyncio.gather(consume(), redraw())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.stdout.write(RESET + "\x1b[?25h\n")
