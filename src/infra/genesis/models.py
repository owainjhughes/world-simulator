from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class World(Base):
    __tablename__ = "worlds"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    seed: Mapped[int]
    width: Mapped[int]
    height: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    world_id: Mapped[UUID] = mapped_column(ForeignKey("worlds.id"))
    name: Mapped[str]
    slug: Mapped[str]
    continent: Mapped[str]
    colour: Mapped[str]
    climate: Mapped[dict] = mapped_column(JSONB)
    tiles: Mapped[list] = mapped_column(JSONB)


class Species(Base):
    __tablename__ = "species"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    world_id: Mapped[UUID] = mapped_column(ForeignKey("worlds.id"))
    region_id: Mapped[UUID] = mapped_column(ForeignKey("regions.id"))
    name: Mapped[str]
    profile: Mapped[dict] = mapped_column(JSONB)
