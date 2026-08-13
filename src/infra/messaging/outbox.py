from uuid import UUID

from sqlalchemy import delete, insert
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from domain.events import Event


class OutboxBase(DeclarativeBase):
    pass


class Outbox(OutboxBase):
    __tablename__ = "outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    aggregateid: Mapped[str]
    routing_key: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)


async def add_events(session: AsyncSession, events: list[Event]) -> None:
    if not events:
        return
    rows = [
        {
            "id": event.event_id,
            "aggregateid": str(event.world_id),
            "routing_key": event.routing_key,
            "payload": event.model_dump(mode="json"),
        }
        for event in events
    ]
    await session.execute(insert(Outbox), rows)
    await session.execute(delete(Outbox))
