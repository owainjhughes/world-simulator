import random
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from sqlalchemy import delete, select

from domain.events import WorldDeleted
from domain.world import generate_world
from infra.genesis.db import Session, engine
from infra.genesis.models import Base, Region, Species, World
from infra.messaging.outbox import OutboxBase, add_events


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(OutboxBase.metadata.create_all)
    yield


app = FastAPI(title="World Genesis", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/worlds")
async def create_world(seed: int | None = None):
    seed = seed if seed is not None else random.randrange(2**31)
    world, regions, species_events = generate_world(seed)

    async with Session() as session:
        session.add(
            World(
                id=world.world_id,
                seed=world.seed,
                width=world.width,
                height=world.height,
            )
        )
        await session.flush()

        session.add_all(
            Region(
                id=region.region_id,
                world_id=world.world_id,
                name=region.name,
                slug=region.slug,
                continent=region.continent,
                colour=region.colour,
                climate=region.climate.model_dump(),
                tiles=region.tiles,
            )
            for region in regions
        )
        await session.flush()

        session.add_all(
            Species(
                id=profile.id,
                world_id=world.world_id,
                region_id=profile.region_id,
                name=profile.name,
                profile=profile.model_dump(mode="json"),
            )
            for event in species_events
            for profile in event.species
        )
        await add_events(session, [world, *regions, *species_events])
        await session.commit()

    return {
        "world_id": world.world_id,
        "seed": seed,
        "regions": world.regions,
        "species": world.species,
    }


@app.delete("/worlds/{world_id}")
async def delete_world(world_id: UUID):
    async with Session() as session:
        world = await session.get(World, world_id)
        if world is None:
            raise HTTPException(status_code=404, detail="world not found")
        await session.execute(delete(Species).where(Species.world_id == world_id))
        await session.execute(delete(Region).where(Region.world_id == world_id))
        await session.delete(world)
        await add_events(session, [WorldDeleted(world_id=world_id)])
        await session.commit()

    return {"deleted": world_id}


@app.get("/worlds")
async def list_worlds():
    async with Session() as session:
        return (await session.scalars(select(World).order_by(World.created_at))).all()


@app.get("/worlds/{world_id}/regions")
async def list_regions(world_id: UUID):
    async with Session() as session:
        regions = (
            await session.scalars(select(Region).where(Region.world_id == world_id))
        ).all()
    if not regions:
        raise HTTPException(status_code=404, detail="world not found")
    return regions


@app.get("/worlds/{world_id}/species")
async def list_species(world_id: UUID):
    async with Session() as session:
        species = (
            await session.scalars(select(Species).where(Species.world_id == world_id))
        ).all()
    if not species:
        raise HTTPException(status_code=404, detail="world not found")
    return [row.profile for row in species]
