import asyncio
import logging
import os
import random
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select

from domain.seasons import (
    DAYS_PER_SEASON,
    HOURS_PER_DAY,
    season_for_day,
    temperature,
)
from domain.weather import update_weather
from infra.clock.db import Session, engine
from infra.clock.models import Base, Region, WorldClock
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
)
from infra.messaging.consumer import EventConsumer
from infra.messaging.publisher import EventPublisher

AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost/")
TICK_SECONDS = float(os.environ.get("TICK_SECONDS", "2"))
LEASE_SECONDS = 30
CLAIM_RETRY_SECONDS = 5
POD_NAME = socket.gethostname()

log = logging.getLogger("clock")


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


async def tick(rng: random.Random, world_id: UUID) -> list[Event]:
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
                    day=clock.day,
                    hour=clock.hour,
                    season=clock.season,
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

    while (world_id := await claim_world()) is None:
        log.info("no world to claim, retrying in %ds", CLAIM_RETRY_SECONDS)
        await asyncio.sleep(CLAIM_RETRY_SECONDS)
    log.info("claimed world %s as %s", world_id, POD_NAME)

    while True:
        await asyncio.sleep(TICK_SECONDS)
        for event in await tick(rng, world_id):
            await publisher.publish(event)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    consumer = EventConsumer(
        AMQP_URL,
        "clock.genesis",
        ["genesis.world.created", "genesis.region.created"],
    )
    await consumer.connect()

    publisher = EventPublisher(AMQP_URL)
    await publisher.connect()

    log.info("clock running, tick every %.1fs", TICK_SECONDS)
    await asyncio.gather(consumer.consume(handle_event), run_clock(publisher))


if __name__ == "__main__":
    asyncio.run(main())
