import asyncio
import json
import os
import subprocess
import sys

import aio_pika
import httpx

GENESIS_URL = os.environ.get("GENESIS_URL", "http://localhost:18800")
AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost:18801/")
SNIFF_SECONDS = 3.0


async def sniff_running() -> dict[str, dict]:
    running: dict[str, dict] = {}
    connection = await aio_pika.connect_robust(AMQP_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            "world.events", aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(exclusive=True)
        await queue.bind(exchange, routing_key="clock.temperature.changed.#")

        async def drain():
            async with queue.iterator() as messages:
                async for message in messages:
                    async with message.process():
                        payload = json.loads(message.body)
                        running[payload["world_id"]] = {
                            "day": payload["day"],
                            "hour": payload["hour"],
                            "season": payload["season"],
                        }

        task = asyncio.create_task(drain())
        await asyncio.sleep(SNIFF_SECONDS)
        task.cancel()
    return running


def fetch_worlds() -> list[dict]:
    with httpx.Client(base_url=GENESIS_URL, timeout=10) as client:
        return client.get("/worlds").json()


def show(worlds: list[dict], running: dict[str, dict]) -> None:
    print()
    print(f"  Arathia worlds ({len(running)} running)")
    if not worlds:
        print("  no worlds yet")
    for index, world in enumerate(worlds, start=1):
        clock = running.get(world["id"])
        status = (
            f"day {clock['day']:>3} {clock['hour']:02d}:00 {clock['season']}"
            if clock
            else "idle"
        )
        print(f"  {index}. {world['id'][:8]}  seed {world['seed']:>10}  {status}")
    print()
    print("  [v]iew N   [c]reate   [d]elete N   [r]efresh   [q]uit")


def pick(worlds: list[dict], argument: str) -> dict | None:
    try:
        return worlds[int(argument) - 1]
    except (ValueError, IndexError):
        print("  give a world number from the list")
        return None


def view(world: dict) -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "app.viewer.main"],
            env={**os.environ, "WORLD_ID": world["id"]},
        )
    except KeyboardInterrupt:
        pass


def create() -> None:
    with httpx.Client(base_url=GENESIS_URL, timeout=30) as client:
        created = client.post("/worlds").json()
    print(f"  created world {created['world_id'][:8]}")
    print("  a free clock pod will claim it within seconds; otherwise it idles until one is free")


def remove(world: dict) -> None:
    answer = input(f"  delete world {world['id'][:8]}? [y/N] ").strip().lower()
    if answer != "y":
        return
    with httpx.Client(base_url=GENESIS_URL, timeout=10) as client:
        client.delete(f"/worlds/{world['id']}")
    print(f"  deleted {world['id'][:8]}")


def main() -> None:
    while True:
        worlds = fetch_worlds()
        running = asyncio.run(sniff_running())
        show(worlds, running)

        try:
            command, _, argument = input("  > ").strip().partition(" ")
        except (KeyboardInterrupt, EOFError):
            print()
            return

        if command == "q":
            return
        if command == "r" or command == "":
            continue
        if command == "c":
            create()
        elif command == "v" and (world := pick(worlds, argument)):
            view(world)
        elif command == "d" and (world := pick(worlds, argument)):
            remove(world)


if __name__ == "__main__":
    main()
