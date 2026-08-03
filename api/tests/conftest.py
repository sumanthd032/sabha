"""Shared test fixtures: fills in the environment config.py requires, and
gives API tests an isolated database and live session manager per test.

These are placeholder values for tests only, never real credentials.
"""

import os
from collections.abc import Iterator

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("GEMINI_API_KEY", "test-placeholder-key")
os.environ.setdefault("QUOTA_RPM", "10")
os.environ.setdefault("QUOTA_RPD", "250")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from sabha.db import get_session
from sabha.main import app
from sabha.routers.live import get_live_manager
from sabha.services.live import LiveSessionManager


@pytest.fixture
def test_engine() -> Engine:
    """A fresh in-memory database per test. StaticPool keeps every Session
    on the same connection, since a plain :memory: database is otherwise
    private to whichever connection created it.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(test_engine: Engine) -> Iterator[TestClient]:
    """A TestClient wired to test_engine, with its own live session manager
    on a short debounce so websocket tests do not wait on the real
    production interval.
    """

    def override_get_session() -> Iterator[Session]:
        with Session(test_engine) as session:
            yield session

    live_manager = LiveSessionManager(engine=test_engine, debounce_seconds=0.05)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_live_manager] = lambda: live_manager
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
