import asyncio
import logging
import os
import random
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException
from sqlalchemy import delete, or_, select

from domain.events import (
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
    WorldDeleted,
)
from domain.seasons import (
    DAWN_HOUR,
    DAYS_PER_SEASON,
    DUSK_HOUR,
    HOURS_PER_DAY,
    is_daytime,
    season_for_day,
    temperature,
)
from domain.weather import update_weather
from infra.clock.db import Session, engine
from infra.clock.models import Base, Region, WorldClock
from infra.messaging.consumer import EventConsumer
from infra.messaging.outbox import OutboxBase, add_events

AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost/")
TICK_SECONDS = float(os.environ.get("TICK_SECONDS", "2"))
LEASE_SECONDS = 30
CLAIM_RETRY_SECONDS = 5
POD_NAME = socket.gethostname()

log = logging.getLogger("clock")

app = FastAPI(title="World Clock")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/worlds/{world_id}/clock")
async def read_clock(world_id: UUID) -> dict:
    async with Session() as session:
        clock = await session.get(WorldClock, world_id)
    if clock is None:
        raise HTTPException(status_code=404, detail="world not found")
    running = (
        clock.claimed_by is not None and clock.lease_expires_at > datetime.now(UTC)
    )
    return {
        "day": clock.day,
        "hour": clock.hour,
        "season": clock.season,
        "running": running,
    }


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
        elif routing_key == "genesis.world.deleted":
            event = WorldDeleted.model_validate(payload)
            await session.execute(
                delete(Region).where(Region.world_id == event.world_id)
            )
            await session.execute(
                delete(WorldClock).where(WorldClock.world_id == event.world_id)
            )
            log.info("removed world %s", event.world_id)
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


async def claim_world() -> UUID | None:
    now = datetime.now(UTC)
    async with Session.begin() as session:
        clock = await session.scalar(
            select(WorldClock)
            .where(
                or_(
                    WorldClock.claimed_by.is_(None),
                    WorldClock.lease_expires_at < now,
                )
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if clock is None:
            return None
        clock.claimed_by = POD_NAME
        clock.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        return clock.world_id


async def tick(rng: random.Random, world_id: UUID) -> None:
    events: list[Event] = []

    async with Session() as session:
        clock = await session.scalar(
            select(WorldClock)
            .where(WorldClock.world_id == world_id, WorldClock.claimed_by == POD_NAME)
            .with_for_update()
        )
        if clock is None:
            raise SystemExit(f"lost lease on world {world_id}")
        clock.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)

        clock.hour += 1
        if clock.hour == HOURS_PER_DAY:
            clock.hour = 0
            clock.day += 1

        if clock.hour == DAWN_HOUR:
            events.append(DayArrived(world_id=clock.world_id, day=clock.day))
        elif clock.hour == DUSK_HOUR:
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
                    day=clock.day,
                    hour=clock.hour,
                    season=clock.season,
                )
            )

            active, started, stopped = update_weather(
                region.weather, region.climate, celsius, rng, is_daytime(clock.hour)
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

        await add_events(session, events)
        await session.commit()


async def run_clock() -> None:
    rng = random.Random()

    while (world_id := await claim_world()) is None:
        log.info("no world to claim, retrying in %ds", CLAIM_RETRY_SECONDS)
        await asyncio.sleep(CLAIM_RETRY_SECONDS)
    log.info("claimed world %s as %s", world_id, POD_NAME)

    while True:
        await asyncio.sleep(TICK_SECONDS)
        await tick(rng, world_id)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(OutboxBase.metadata.create_all)

    consumer = EventConsumer(
        AMQP_URL,
        "clock.genesis",
        ["genesis.world.created", "genesis.world.deleted", "genesis.region.created"],
    )
    await consumer.connect()

    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=8000, access_log=False)
    )

    log.info("clock running, tick every %.1fs", TICK_SECONDS)
    await asyncio.gather(consumer.consume(handle_event), run_clock(), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
