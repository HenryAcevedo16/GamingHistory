from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

engine = create_engine(
    settings.resolved_database_url,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


def init_db() -> None:
    """Create tables. Imports models so SQLModel metadata is populated."""
    from app.editing import persistence  # noqa: F401
    from app.models import audit, plugin  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
