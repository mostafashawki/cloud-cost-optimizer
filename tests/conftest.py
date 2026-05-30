"""Shared pytest fixtures.

`isolated_db`
    Repoints `app.db.engine` + `app.db.SessionLocal` at a per-test SQLite
    file under `tmp_path` BEFORE the test runs, so the real
    `<repo>/app.db` is never touched. Tables are created up-front so any
    test that doesn't fire the FastAPI lifespan can still write rows.
    Auto-reverts after the test via `monkeypatch`.

`client`
    A `TestClient(app)` used as a context manager so the FastAPI
    `lifespan` actually fires (which re-runs `init_db()` against the
    monkey-patched engine — that's the production code path).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Swap the project-level SQLite engine for a per-test one."""
    test_db = tmp_path / "test_app.db"
    url = f"sqlite:///{test_db}"
    new_engine = create_engine(
        url, future=True, connect_args={"check_same_thread": False}
    )
    new_session = sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True
    )

    from app import db as app_db

    monkeypatch.setattr(app_db, "engine", new_engine)
    monkeypatch.setattr(app_db, "SessionLocal", new_session)

    # `init_db()` looks up `engine` from the module namespace at call time,
    # so this picks up the monkey-patched value.
    app_db.init_db()

    yield


@pytest.fixture
def client(isolated_db: None) -> Iterator[TestClient]:
    """TestClient bound to the FastAPI app, with the DB swapped out."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
