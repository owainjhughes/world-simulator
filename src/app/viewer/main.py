import asyncio
import json
import os
import sys

import aio_pika
import httpx

GENESIS_URL = os.environ.get("GENESIS_URL", "http://localhost:8000")
AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost/")
REFRESH_SECONDS = 0.5

PALETTE = [27, 250, 244, 34, 54, 127, 41, 220, 22, 37]
RESET = "\x1b[0m"

world = {"width": 0, "height": 0, "grid": [], "regions": {}, "order": []}
now = {"day": 0, "hour": 0, "season": "winter"}


def paint(colour: int) -> str:
    return f"\x1b[48;5;{colour}m \x1b[49m"


async def load_world() -> None:
    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=10) as client:
        worlds = (await client.get("/worlds")).json()
        if not worlds:
            sys.exit("no world yet - create one with: curl -X POST %s/worlds" % GENESIS_URL)
        latest = worlds[-1]
        regions = (await client.get(f"/worlds/{latest['id']}/regions")).json()

    world["width"] = latest["width"]
    world["height"] = latest["height"]
    world["grid"] = [[0] * latest["width"] for _ in range(latest["height"])]

    for index, region in enumerate(regions):
        slug = region["slug"]
        world["order"].append(slug)
        world["regions"][slug] = {
            "name": region["name"],
            "colour": PALETTE[index % len(PALETTE)],
            "celsius": None,
            "weather": set(),
        }
        for x, y in region["tiles"]:
            world["grid"][y][x] = PALETTE[index % len(PALETTE)]


def render() -> None:
    lines = [
        f"  Arathia   day {now['day']}  {now['hour']:02d}:00  {now['season']}",
        "",
    ]

    legend = []
    for slug in world["order"]:
        region = world["regions"][slug]
        celsius = "     -" if region["celsius"] is None else f"{region['celsius']:6.1f}C"
        weather = " ".join(sorted(region["weather"])) or ""
        legend.append(
            f"{paint(region['colour'])}{RESET} {region['name']:<16}{celsius}  {weather}"
        )

    for y, row in enumerate(world["grid"]):
        map_line = "  " + "".join(paint(colour) for colour in row)
        side = f"   {legend[y]}" if y < len(legend) else ""
        lines.append(map_line + side)

    sys.stdout.write("\x1b[H\x1b[2J" + "\n".join(lines) + "\n")
    sys.stdout.flush()


def apply_event(routing_key: str, payload: dict) -> None:
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
        sys.stdout.write(RESET + "\n")
