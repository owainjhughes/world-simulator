import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://dev:dev@localhost:5434/ecology"
)

engine = create_async_engine(DATABASE_URL)
Session = async_sessionmaker(engine, expire_on_commit=False)
