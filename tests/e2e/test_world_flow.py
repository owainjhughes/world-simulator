import asyncio
import json
import os
from uuid import uuid4

import aio_pika
import httpx
import pytest

from domain.atlas import REGIONS
from domain.seasons import SEASONS

GENESIS_URL = os.environ.get("GENESIS_URL", "http://localhost:18800")
CLOCK_URL = os.environ.get("CLOCK_URL", "http://localhost:18805")
AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost:18801/")
EVENT_TIMEOUT = 90

REGION_COUNT = len(REGIONS)
CREATION_EVENTS = 1 + REGION_COUNT * 2

pytestmark = pytest.mark.e2e


async def collect(
    routing_key: str, seconds: float, listening: asyncio.Event
) -> list[tuple[str, dict]]:
    connection = await aio_pika.connect_robust(AMQP_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            "world.events", aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(exclusive=True)
        await queue.bind(exchange, routing_key=routing_key)

        received = []

        async def drain():
            async with queue.iterator() as messages:
                listening.set()
                async for message in messages:
                    async with message.process():
                        received.append(
                            (message.routing_key, json.loads(message.body))
                        )

        task = asyncio.create_task(drain())
        await asyncio.sleep(seconds)
        task.cancel()
        return received


async def ensure_worlds() -> list[dict]:
    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=30) as client:
        worlds = (await client.get("/worlds")).json()
        if not worlds:
            await client.post("/worlds")
            worlds = (await client.get("/worlds")).json()
    return worlds


async def test_genesis_creates_a_complete_world():
    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=30) as client:
        created = (await client.post("/worlds")).json()
        world_id = created["world_id"]

        assert created["regions"] == REGION_COUNT
        assert created["species"] > 0

        regions = (await client.get(f"/worlds/{world_id}/regions")).json()
        species = (await client.get(f"/worlds/{world_id}/species")).json()

    assert len(regions) == REGION_COUNT
    assert all(region["tiles"] for region in regions)
    assert all(region["colour"].startswith("#") for region in regions)
    assert len(species) == created["species"]
    assert {s["region_id"] for s in species} == {r["id"] for r in regions}


async def test_creating_a_world_announces_it_on_the_broker():
    listening = asyncio.Event()
    listener = asyncio.create_task(collect("genesis.#", 15, listening))
    await listening.wait()

    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=30) as client:
        created = (await client.post("/worlds")).json()

    events = await listener
    kinds = [payload["event_type"] for _, payload in events]
    mine = [p for _, p in events if p["world_id"] == created["world_id"]]

    assert "WorldCreated" in kinds
    assert kinds.count("RegionCreated") >= REGION_COUNT
    assert len(mine) == CREATION_EVENTS


async def test_the_clock_runs_exactly_one_world_across_all_regions():
    await ensure_worlds()

    seen: dict[str, set[str]] = {}

    async def watch():
        connection = await aio_pika.connect_robust(AMQP_URL)
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                "world.events", aio_pika.ExchangeType.TOPIC, durable=True
            )
            queue = await channel.declare_queue(exclusive=True)
            await queue.bind(exchange, routing_key="clock.temperature.changed.#")

            async with queue.iterator() as messages:
                async for message in messages:
                    async with message.process():
                        payload = json.loads(message.body)
                        seen.setdefault(payload["world_id"], set()).add(
                            payload["region_slug"]
                        )
                        if len(seen[payload["world_id"]]) == REGION_COUNT:
                            return

    await asyncio.wait_for(watch(), timeout=EVENT_TIMEOUT)
    assert len(seen) == 1


async def test_deleting_a_world_removes_it_and_announces_it():
    listening = asyncio.Event()
    listener = asyncio.create_task(collect("genesis.world.deleted", 8, listening))
    await listening.wait()

    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=30) as client:
        created = (await client.post("/worlds")).json()
        world_id = created["world_id"]

        deleted = (await client.delete(f"/worlds/{world_id}")).json()
        assert deleted["deleted"] == world_id

        worlds = (await client.get("/worlds")).json()
        assert world_id not in {world["id"] for world in worlds}
        assert (await client.get(f"/worlds/{world_id}/regions")).status_code == 404

    events = await listener
    assert world_id in {payload["world_id"] for _, payload in events}


async def test_the_clock_endpoint_reports_time_for_a_running_world():
    worlds = await ensure_worlds()

    async def poll():
        async with httpx.AsyncClient(base_url=CLOCK_URL, timeout=10) as client:
            while True:
                for world in worlds:
                    response = await client.get(f"/worlds/{world['id']}/clock")
                    if response.status_code == 200 and response.json()["running"]:
                        return response.json()
                await asyncio.sleep(1)

    state = await asyncio.wait_for(poll(), timeout=EVENT_TIMEOUT)
    assert state["season"] in SEASONS
    assert 0 <= state["hour"] < 24
    assert state["day"] >= 0


async def test_the_clock_endpoint_404s_for_unknown_worlds():
    async with httpx.AsyncClient(base_url=CLOCK_URL, timeout=10) as client:
        response = await client.get(f"/worlds/{uuid4()}/clock")
    assert response.status_code == 404


async def test_region_routing_keys_deliver_only_that_region():
    events = await collect("clock.#.wylenn", 10, asyncio.Event())
    assert events, "no wylenn events seen - is the clock running?"
    assert {payload["region_slug"] for _, payload in events} == {"wylenn"}


async def test_ecology_counts_every_region_and_puts_creatures_in_them():
    await ensure_worlds()

    censuses: dict[str, dict] = {}

    async def watch():
        connection = await aio_pika.connect_robust(AMQP_URL)
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                "world.events", aio_pika.ExchangeType.TOPIC, durable=True
            )
            queue = await channel.declare_queue(exclusive=True)
            await queue.bind(exchange, routing_key="ecology.census.#")

            async with queue.iterator() as messages:
                async for message in messages:
                    async with message.process():
                        payload = json.loads(message.body)
                        censuses[payload["region_slug"]] = payload
                        if len(censuses) == REGION_COUNT:
                            return

    await asyncio.wait_for(watch(), timeout=EVENT_TIMEOUT)

    assert len(censuses) == REGION_COUNT
    assert all(
        any(payload.get(diet) for diet in ("herbivores", "carnivores", "omnivores"))
        for payload in censuses.values()
    )


async def test_ecology_routing_keys_deliver_only_that_region():
    events = await collect("ecology.#.wylenn", 12, asyncio.Event())
    assert events, "no wylenn ecology events seen - is ecology running?"
    assert {payload["region_slug"] for _, payload in events} == {"wylenn"}
