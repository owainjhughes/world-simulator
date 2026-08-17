from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Pod(Base):
    __tablename__ = "pods"

    name: Mapped[str] = mapped_column(primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class World(Base):
    __tablename__ = "worlds"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    seed: Mapped[int]
    regions: Mapped[int]
    species: Mapped[int]
    seeded: Mapped[bool]


class RegionShard(Base):
    __tablename__ = "region_shards"

    world_id: Mapped[UUID] = mapped_column(primary_key=True)
    region_id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    climate: Mapped[dict] = mapped_column(JSONB)
    tiles: Mapped[list] = mapped_column(JSONB)
    vegetation: Mapped[list] = mapped_column(JSONB)
    comfort: Mapped[dict] = mapped_column(JSONB)
    claimed_by: Mapped[str | None]


class Species(Base):
    __tablename__ = "species"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    world_id: Mapped[UUID]
    region_id: Mapped[UUID]
    profile: Mapped[dict] = mapped_column(JSONB)


class Creature(Base):
    __tablename__ = "creatures"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    world_id: Mapped[UUID]
    region_id: Mapped[UUID]
    species_id: Mapped[UUID]
    x: Mapped[int]
    y: Mapped[int]
    hunger: Mapped[float]
    stress: Mapped[float]
    age: Mapped[int]
    lifespan: Mapped[int]
    cooldown: Mapped[int]

    __table_args__ = (Index("ix_creatures_region", "world_id", "region_id"),)
