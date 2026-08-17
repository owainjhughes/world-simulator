import asyncio
import logging
import os
import random
import socket
from datetime import UTC, datetime, timedelta

import uvicorn
from fastapi import FastAPI
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from domain import ecology
from domain.events import (
    Climate,
    ComfortChanged,
    CreatureBorn,
    CreatureDied,
    Event,
    RegionCensus,
    RegionCreated,
    SpeciesExtinct,
    SpeciesGenerated,
    SpeciesProfile,
    TemperatureChanged,
    WorldCreated,
    WorldDeleted,
)
from infra.ecology.db import Session, engine
from infra.ecology.models import Base, Creature, Pod, RegionShard, Species, World
from infra.messaging.consumer import EventConsumer
from infra.messaging.outbox import OutboxBase, add_events

AMQP_URL = os.environ.get("AMQP_URL", "amqp://dev:dev@localhost/")
CLAIM_SECONDS = float(os.environ.get("CLAIM_SECONDS", "2"))
POD_TTL_SECONDS = 15
POD_NAME = socket.gethostname()

log = logging.getLogger("ecology")

app = FastAPI(title="World Ecology")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


async def handle_genesis(routing_key: str, payload: dict) -> None:
    async with Session() as session:
        if routing_key == "genesis.region.created":
            event = RegionCreated.model_validate(payload)
            await _record(
                session,
                RegionShard,
                [
                    {
                        "world_id": event.world_id,
                        "region_id": event.region_id,
                        "name": event.name,
                        "slug": event.slug,
                        "climate": event.climate.model_dump(),
                        "tiles": event.tiles,
                        "vegetation": [1.0] * len(event.tiles),
                        "comfort": {},
                        "claimed_by": None,
                    }
                ],
            )
        elif routing_key == "genesis.species.generated":
            event = SpeciesGenerated.model_validate(payload)
            await _record(
                session,
                Species,
                [
                    {
                        "id": profile.id,
                        "world_id": event.world_id,
                        "region_id": event.region_id,
                        "profile": profile.model_dump(mode="json"),
                    }
                    for profile in event.species
                ],
            )
        elif routing_key == "genesis.world.created":
            event = WorldCreated.model_validate(payload)
            await _record(
                session,
                World,
                [
                    {
                        "id": event.world_id,
                        "seed": event.seed,
                        "regions": event.regions,
                        "species": event.species,
                        "seeded": False,
                    }
                ],
            )
        elif routing_key == "genesis.world.deleted":
            event = WorldDeleted.model_validate(payload)
            for model in (Creature, Species, RegionShard):
                await session.execute(
                    delete(model).where(model.world_id == event.world_id)
                )
            await session.execute(delete(World).where(World.id == event.world_id))
            log.info("removed world %s", event.world_id)

        await session.commit()


async def _record(session, model, rows: list[dict]) -> None:
    await session.execute(insert(model).values(rows).on_conflict_do_nothing())


async def seed_pending() -> None:
    async with Session.begin() as session:
        waiting = list(
            await session.scalars(
                select(World).where(World.seeded.is_(False)).with_for_update(skip_locked=True)
            )
        )

        for world in waiting:
            shards = list(
                await session.scalars(
                    select(RegionShard).where(RegionShard.world_id == world.id)
                )
            )
            rows = list(
                await session.scalars(
                    select(Species).where(Species.world_id == world.id)
                )
            )
            if len(shards) < world.regions or len(rows) < world.species:
                continue

            seed_world(session, world, shards, rows)


def seed_world(session, world: World, shards: list, rows: list) -> None:
    profiles = [SpeciesProfile.model_validate(row.profile) for row in rows]
    regions = [
        ecology.Region(
            region_id=shard.region_id,
            climate=Climate.model_validate(shard.climate),
            tiles=[tuple(tile) for tile in shard.tiles],
        )
        for shard in shards
    ]

    spawned = ecology.populate(random.Random(world.seed), profiles, regions)
    for shard in shards:
        session.add_all(_row(creature, shard) for creature in spawned[shard.region_id])
    world.seeded = True

    log.info(
        "seeded world %s with %d creatures across %d regions",
        world.id,
        sum(len(born) for born in spawned.values()),
        len(regions),
    )


async def handle_tick(routing_key: str, payload: dict) -> None:
    event = TemperatureChanged.model_validate(payload)

    async with Session() as session:
        shard = await session.get(
            RegionShard, (event.world_id, event.region_id), with_for_update=True
        )
        if shard is None or shard.claimed_by != POD_NAME:
            return

        rows = (
            await session.scalars(
                select(Creature).where(
                    Creature.world_id == event.world_id,
                    Creature.region_id == event.region_id,
                )
            )
        ).all()

        species = {
            row.id: SpeciesProfile.model_validate(row.profile)
            for row in (
                await session.scalars(
                    select(Species).where(
                        Species.id.in_({row.species_id for row in rows})
                    )
                )
            ).all()
        }

        result = ecology.step_region(
            [
                ecology.Creature(
                    id=row.id,
                    species_id=row.species_id,
                    x=row.x,
                    y=row.y,
                    hunger=row.hunger,
                    stress=row.stress,
                    age=row.age,
                    lifespan=row.lifespan,
                    cooldown=row.cooldown,
                )
                for row in rows
            ],
            species,
            [tuple(tile) for tile in shard.tiles],
            list(shard.vegetation),
            Climate.model_validate(shard.climate),
            event.celsius,
            event.season,
            shard.comfort,
            random.Random(),
        )

        dead = _persist(session, shard, rows, result)
        if dead:
            await session.execute(delete(Creature).where(Creature.id.in_(dead)))
        shard.vegetation = result.vegetation
        shard.comfort = {**shard.comfort, **result.comfort}

        await add_events(session, _describe(shard, event, result, species))
        await session.commit()


def _row(creature: ecology.Creature, shard: RegionShard) -> Creature:
    return Creature(
        id=creature.id,
        world_id=shard.world_id,
        region_id=shard.region_id,
        species_id=creature.species_id,
        x=creature.x,
        y=creature.y,
        hunger=creature.hunger,
        stress=creature.stress,
        age=creature.age,
        lifespan=creature.lifespan,
        cooldown=creature.cooldown,
    )


def _persist(session, shard: RegionShard, rows, result: ecology.StepResult) -> list:
    known = {row.id: row for row in rows}

    for creature in result.creatures:
        row = known.pop(creature.id, None)
        if row is None:
            session.add(_row(creature, shard))
            continue
        row.x, row.y = creature.x, creature.y
        row.hunger, row.stress = creature.hunger, creature.stress
        row.age, row.cooldown = creature.age, creature.cooldown

    return list(known)


def _describe(
    shard: RegionShard,
    event: TemperatureChanged,
    result: ecology.StepResult,
    species: dict,
) -> list[Event]:
    where = {
        "world_id": shard.world_id,
        "region_id": shard.region_id,
        "region_slug": shard.slug,
        "region_name": shard.name,
    }
    events: list[Event] = [
        RegionCensus(
            **where,
            day=event.day,
            hour=event.hour,
            **ecology.census(result.creatures, species),
        )
    ]
    events.extend(CreatureBorn(**where, species=name) for name in result.born)
    events.extend(
        CreatureDied(
            **where, species=death.species, cause=death.cause, killed_by=death.killed_by
        )
        for death in result.deaths
    )
    events.extend(SpeciesExtinct(**where, species=name) for name in result.extinct)
    events.extend(
        ComfortChanged(
            **where,
            species=name,
            state="stressed" if stressed else "eased",
            celsius=event.celsius,
        )
        for name, stressed in result.comfort.items()
    )
    return events


async def rebalance() -> set[str]:
    now = datetime.now(UTC)

    async with Session.begin() as session:
        await session.merge(Pod(name=POD_NAME, seen_at=now))
        await session.execute(
            delete(Pod).where(Pod.seen_at < now - timedelta(seconds=POD_TTL_SECONDS))
        )

        pods = list(await session.scalars(select(Pod.name).order_by(Pod.name)))
        total = await session.scalar(select(func.count()).select_from(RegionShard))
        mine = list(
            await session.scalars(
                select(RegionShard).where(RegionShard.claimed_by == POD_NAME)
            )
        )
        rank = pods.index(POD_NAME)
        share = total // len(pods) + (rank < total % len(pods))

        if len(mine) > share:
            for shard in mine[share:]:
                shard.claimed_by = None
            mine = mine[:share]
        elif len(mine) < share:
            free = list(
                await session.scalars(
                    select(RegionShard)
                    .where(
                        RegionShard.claimed_by.is_(None)
                        | RegionShard.claimed_by.notin_(select(Pod.name))
                    )
                    .limit(share - len(mine))
                    .with_for_update(skip_locked=True)
                )
            )
            for shard in free:
                shard.claimed_by = POD_NAME
            mine.extend(free)

        return {shard.slug for shard in mine}


async def follow_regions(consumer: EventConsumer) -> None:
    held: set[str] = set()

    while True:
        await seed_pending()
        slugs = await rebalance()
        for slug in slugs - held:
            await consumer.bind(f"clock.temperature.changed.{slug}")
        for slug in held - slugs:
            await consumer.unbind(f"clock.temperature.changed.{slug}")
        if slugs != held:
            log.info("holding %d regions: %s", len(slugs), " ".join(sorted(slugs)))
        held = slugs
        await asyncio.sleep(CLAIM_SECONDS)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    async with engine.begin() as connection:
        await connection.execute(text("SELECT pg_advisory_xact_lock(4801)"))
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(OutboxBase.metadata.create_all)

    genesis = EventConsumer(
        AMQP_URL,
        "ecology.genesis",
        [
            "genesis.region.created",
            "genesis.species.generated",
            "genesis.world.created",
            "genesis.world.deleted",
        ],
    )
    await genesis.connect()

    ticks = EventConsumer(AMQP_URL, "ecology.ticks", [], exclusive=True)
    await ticks.connect()

    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=8000, access_log=False)
    )

    log.info("ecology running as %s", POD_NAME)
    await asyncio.gather(
        genesis.consume(handle_genesis),
        ticks.consume(handle_tick),
        follow_regions(ticks),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
