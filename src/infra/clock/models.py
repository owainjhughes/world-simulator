from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WorldClock(Base):
    __tablename__ = "world_clocks"

    world_id: Mapped[UUID] = mapped_column(primary_key=True)
    day: Mapped[int]
    hour: Mapped[int]
    season: Mapped[str]
    claimed_by: Mapped[str | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    world_id: Mapped[UUID]
    name: Mapped[str]
    slug: Mapped[str]
    climate: Mapped[dict] = mapped_column(JSONB)
    weather: Mapped[list] = mapped_column(JSONB, default=list)
