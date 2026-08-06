import asyncio
import json
import os

import aio_pika
import httpx
import pytest

GENESIS_URL = os.environ.get("GENESIS_URL", "http://localhost:8000")
AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost/")
EVENT_TIMEOUT = 60

pytestmark = pytest.mark.e2e


async def collect(routing_key: str, seconds: float) -> list[tuple[str, dict]]:
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
                async for message in messages:
                    async with message.process():
                        received.append(
                            (message.routing_key, json.loads(message.body))
                        )

        task = asyncio.create_task(drain())
        await asyncio.sleep(seconds)
        task.cancel()
        return received


async def test_genesis_creates_a_complete_world():
    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=30) as client:
        created = (await client.post("/worlds")).json()
        world_id = created["world_id"]

        assert created["regions"] == 10
        assert created["species"] > 0

        regions = (await client.get(f"/worlds/{world_id}/regions")).json()
        species = (await client.get(f"/worlds/{world_id}/species")).json()

    assert len(regions) == 10
    assert all(region["tiles"] for region in regions)
    assert len(species) == created["species"]
    assert {s["region_id"] for s in species} == {r["id"] for r in regions}


async def test_creating_a_world_announces_it_on_the_broker():
    listener = asyncio.create_task(collect("genesis.#", 15))
    await asyncio.sleep(1)

    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=30) as client:
        created = (await client.post("/worlds")).json()

    events = await listener
    kinds = [payload["event_type"] for _, payload in events]
    mine = [p for _, p in events if p["world_id"] == created["world_id"]]

    assert "WorldCreated" in kinds
    assert kinds.count("RegionCreated") >= 10
    assert len(mine) == 21


async def test_the_clock_picks_up_a_new_world_and_starts_running_it():
    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=30) as client:
        created = (await client.post("/worlds")).json()

    world_id = created["world_id"]
    seen_regions: set[str] = set()

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
                        if payload["world_id"] == world_id:
                            seen_regions.add(payload["region_slug"])
                        if len(seen_regions) == 10:
                            return

    await asyncio.wait_for(watch(), timeout=EVENT_TIMEOUT)
    assert len(seen_regions) == 10


async def test_region_routing_keys_deliver_only_that_region():
    events = await collect("clock.#.wylenn", 10)
    assert events, "no wylenn events seen - is the clock running?"
    assert {payload["region_slug"] for _, payload in events} == {"wylenn"}
