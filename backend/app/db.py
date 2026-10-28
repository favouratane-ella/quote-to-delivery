"""Database engine and session factory. SQLite by default, Postgres in production."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (registers tables)

    Base.metadata.create_all(engine)
    ensure_columns()


def ensure_columns() -> None:
    """Add columns that newer versions of the app expect to databases created by older versions."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(dialect=engine.dialect)}"
                if col.server_default is not None:
                    ddl += f" DEFAULT '{col.server_default.arg}'"
                conn.execute(text(ddl))
