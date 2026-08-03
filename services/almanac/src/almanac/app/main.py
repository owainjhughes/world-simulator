import asyncio
import logging
import os
import random
from uuid import UUID

import httpx
from sqlalchemy import select

from almanac.domain.clock import (
    DAYS_PER_SEASON,
    HOURS_PER_DAY,
    season_for_day,
    temperature,
)
from almanac.domain.weather import update_weather
from almanac.infra.db import Session, engine
from almanac.infra.models import Base, Region, WorldClock
from contracts.events import (
    DayArrived,
    Event,
    NightArrived,
    RegionCreated,
    SeasonChanged,
    SeasonProgressed,
    TemperatureChanged,
    WeatherStarted,
    WeatherStopped,
    WorldCreated,
)
from messaging.consumer import EventConsumer
from messaging.publisher import EventPublisher

AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost/")
GENESIS_URL = os.environ.get("GENESIS_URL", "http://localhost:8000")
TICK_SECONDS = float(os.environ.get("TICK_SECONDS", "2"))

log = logging.getLogger("almanac")


async def handle_event(routing_key: str, payload: dict) -> None:
    async with Session() as session:
        if routing_key == "genesis.world.created":
            event = WorldCreated.model_validate(payload)
            await session.merge(
                WorldClock(
                    world_id=event.world_id, day=0, hour=0, season=season_for_day(0)
                )
            )
            log.info("registered world %s", event.world_id)
        elif routing_key == "genesis.region.created":
            event = RegionCreated.model_validate(payload)
            await session.merge(
                Region(
                    id=event.region_id,
                    world_id=event.world_id,
                    name=event.name,
                    slug=event.slug,
                    climate=event.climate.model_dump(),
                    weather=[],
                )
            )
            log.info("registered region %s", event.name)
        await session.commit()


async def bootstrap() -> None:
    async with Session() as session:
        if await session.scalar(select(WorldClock).limit(1)):
            return

    async with httpx.AsyncClient(base_url=GENESIS_URL, timeout=5) as client:
        worlds = (await client.get("/worlds")).json()
        if not worlds:
            log.info("genesis has no world yet, waiting for events")
            return
        world = worlds[-1]
        regions = (await client.get(f"/worlds/{world['id']}/regions")).json()

    async with Session() as session:
        session.add(
            WorldClock(
                world_id=UUID(world["id"]), day=0, hour=0, season=season_for_day(0)
            )
        )
        session.add_all(
            Region(
                id=UUID(region["id"]),
                world_id=UUID(world["id"]),
                name=region["name"],
                slug=region["slug"],
                climate=region["climate"],
                weather=[],
            )
            for region in regions
        )
        await session.commit()

    log.info(
        "bootstrapped world %s with %d regions from genesis", world["id"], len(regions)
    )


async def tick(rng: random.Random) -> list[Event]:
    events: list[Event] = []

    async with Session() as session:
        clocks = (await session.scalars(select(WorldClock))).all()

        for clock in clocks:
            clock.hour += 1
            if clock.hour == HOURS_PER_DAY:
                clock.hour = 0
                clock.day += 1

            if clock.hour == 6:
                events.append(DayArrived(world_id=clock.world_id, day=clock.day))
            elif clock.hour == 18:
                events.append(NightArrived(world_id=clock.world_id, day=clock.day))

            if clock.hour == 0:
                season = season_for_day(clock.day)
                if season != clock.season:
                    clock.season = season
                    events.append(
                        SeasonChanged(
                            world_id=clock.world_id, season=season, day=clock.day
                        )
                    )
                    log.info("season changed to %s on day %d", season, clock.day)
                events.append(
                    SeasonProgressed(
                        world_id=clock.world_id,
                        season=season,
                        day=clock.day,
                        day_of_season=clock.day % DAYS_PER_SEASON,
                    )
                )

            regions = (
                await session.scalars(
                    select(Region).where(Region.world_id == clock.world_id)
                )
            ).all()

            for region in regions:
                celsius = temperature(region.climate, clock.day, clock.hour, rng)
                events.append(
                    TemperatureChanged(
                        world_id=clock.world_id,
                        region_id=region.id,
                        region_slug=region.slug,
                        region_name=region.name,
                        celsius=celsius,
                    )
                )

                active, started, stopped = update_weather(
                    region.weather, region.climate, celsius, rng
                )
                if started or stopped:
                    region.weather = active
                for condition in started:
                    events.append(
                        WeatherStarted(
                            world_id=clock.world_id,
                            region_id=region.id,
                            region_slug=region.slug,
                            region_name=region.name,
                            condition=condition,
                        )
                    )
                for condition in stopped:
                    events.append(
                        WeatherStopped(
                            world_id=clock.world_id,
                            region_id=region.id,
                            region_slug=region.slug,
                            region_name=region.name,
                            condition=condition,
                        )
                    )

            log.info(
                "day %d %02d:00 %s - %d regions, %d events",
                clock.day,
                clock.hour,
                clock.season,
                len(regions),
                len(events),
            )

        await session.commit()

    return events


async def run_clock(publisher: EventPublisher) -> None:
    rng = random.Random()
    while True:
        await asyncio.sleep(TICK_SECONDS)
        for event in await tick(rng):
            await publisher.publish(event)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    consumer = EventConsumer(
        AMQP_URL,
        "almanac.genesis",
        ["genesis.world.created", "genesis.region.created"],
    )
    await consumer.connect()

    await bootstrap()

    publisher = EventPublisher(AMQP_URL)
    await publisher.connect()

    log.info("almanac running, tick every %.1fs", TICK_SECONDS)
    await asyncio.gather(consumer.consume(handle_event), run_clock(publisher))


asyncio.run(main())
