from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DB_PATH = Path(__file__).resolve().parent.parent / "app.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"


engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Single declarative base for every ORM model in the project."""


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (idempotent)."""
    # Importing models here ensures their classes are registered with `Base.metadata`
    # before `create_all` runs. The module is intentionally empty until T1.
    from app import models  # noqa: F401  (import for side-effect: model registration)

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session and guarantees close."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
