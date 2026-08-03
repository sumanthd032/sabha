"""Fifty participants voting at once must not stall on each other or on
the refit their votes trigger.

Uses its own file backed database rather than the shared in-memory
test_engine fixture: a single in-memory SQLite connection is one
logical connection shared by every session, and true concurrent
threads driving separate SQLAlchemy sessions against it interleave
transactions incorrectly. A temp file with SQLAlchemy's normal pool
gives each concurrent request its own connection, which is what a real
deployment looks like too.
"""

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from sabha.db import get_session
from sabha.main import app
from sabha.routers.live import get_live_manager
from sabha.seed.loader import load_seed
from sabha.services.live import LiveSessionManager
from sabha.services.model_run import latest_model_run

NUM_VOTERS = 50


@pytest.fixture
def file_backed_client(tmp_path: Path) -> Iterator[tuple[TestClient, Engine]]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrency.db'}",
        connect_args={"timeout": 30},
        pool_size=NUM_VOTERS + 5,
        max_overflow=10,
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    live_manager = LiveSessionManager(engine=engine, debounce_seconds=0.05)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_live_manager] = lambda: live_manager
    with TestClient(app) as test_client:
        yield test_client, engine
    app.dependency_overrides.clear()


def _seed_small_consultation(engine: Engine) -> int:
    with Session(engine) as session:
        load_seed(session, num_participants=10, seed=2)
    return 1


def _join_and_vote(client: TestClient, consultation_id: int, voter_index: int) -> int:
    join_response = client.post(f"/api/consultations/{consultation_id}/join")
    assert join_response.status_code == 200, join_response.text
    session_token = join_response.json()["session_token"]

    next_response = client.get(
        f"/api/consultations/{consultation_id}/statements/next",
        params={"session_token": session_token},
    )
    assert next_response.status_code == 200, next_response.text
    statement = next_response.json()
    assert statement is not None

    vote_response = client.post(
        f"/api/consultations/{consultation_id}/votes",
        json={
            "session_token": session_token,
            "statement_id": statement["id"],
            "value": 1 if voter_index % 2 == 0 else -1,
        },
    )
    return int(vote_response.status_code)


def test_fifty_concurrent_voters_do_not_stall_the_refit(
    file_backed_client: tuple[TestClient, Engine],
) -> None:
    client, engine = file_backed_client
    consultation_id = _seed_small_consultation(engine)

    started_at = time.monotonic()
    with ThreadPoolExecutor(max_workers=NUM_VOTERS) as pool:
        statuses = list(
            pool.map(
                lambda i: _join_and_vote(client, consultation_id, i),
                range(NUM_VOTERS),
            )
        )
    elapsed = time.monotonic() - started_at

    assert statuses == [200] * NUM_VOTERS
    assert elapsed < 15.0

    deadline = time.monotonic() + 3.0
    model_run = None
    while time.monotonic() < deadline:
        with Session(engine) as session:
            model_run = latest_model_run(session, consultation_id)
        if model_run is not None:
            break
        time.sleep(0.05)

    assert model_run is not None
    assert len(model_run.participant_biases) >= NUM_VOTERS
