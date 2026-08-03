"""Tests for the plain REST surface: consultations, statements, joining,
voting, and rankings, including the error paths a client can hit.
"""

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from sabha.seed.loader import load_seed


def _seed_small_consultation(engine: Engine) -> int:
    with Session(engine) as session:
        load_seed(session, num_participants=5, seed=3)
    return 1


def test_unknown_consultation_returns_404(client: TestClient) -> None:
    assert client.get("/api/consultations/999").status_code == 404
    assert client.get("/api/consultations/999/statements").status_code == 404
    assert client.post("/api/consultations/999/join").status_code == 404


def test_list_and_get_consultation(client: TestClient, test_engine: Engine) -> None:
    consultation_id = _seed_small_consultation(test_engine)

    listing = client.get("/api/consultations")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["is_synthetic"] is True

    single = client.get(f"/api/consultations/{consultation_id}")
    assert single.status_code == 200
    assert single.json()["id"] == consultation_id


def test_list_statements_for_a_consultation(client: TestClient, test_engine: Engine) -> None:
    consultation_id = _seed_small_consultation(test_engine)

    statements = client.get(f"/api/consultations/{consultation_id}/statements")
    assert statements.status_code == 200
    assert len(statements.json()) > 0
    assert all(s["code"].startswith("S-") for s in statements.json())


def test_join_then_vote_with_an_unknown_token_is_rejected(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_small_consultation(test_engine)

    response = client.post(
        f"/api/consultations/{consultation_id}/votes",
        json={"session_token": "not-a-real-token", "statement_id": 1, "value": 1},
    )
    assert response.status_code == 404


def test_voting_twice_on_the_same_statement_is_rejected(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_small_consultation(test_engine)
    session_token = client.post(f"/api/consultations/{consultation_id}/join").json()[
        "session_token"
    ]
    statement_id = client.get(
        f"/api/consultations/{consultation_id}/statements/next",
        params={"session_token": session_token},
    ).json()["id"]

    payload = {"session_token": session_token, "statement_id": statement_id, "value": 1}
    first = client.post(f"/api/consultations/{consultation_id}/votes", json=payload)
    second = client.post(f"/api/consultations/{consultation_id}/votes", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409


def test_rankings_are_empty_before_any_model_run_exists(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_small_consultation(test_engine)

    rankings = client.get(f"/api/consultations/{consultation_id}/rankings")
    assert rankings.status_code == 200
    body = rankings.json()
    assert body["model_run_id"] is None
    assert body["bridging"] == []
    assert body["majority"] == []

    assert client.get(f"/api/consultations/{consultation_id}/model-runs/latest").status_code == 404


def test_next_statement_never_repeats_for_the_same_participant(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_small_consultation(test_engine)
    session_token = client.post(f"/api/consultations/{consultation_id}/join").json()[
        "session_token"
    ]

    seen: set[int] = set()
    for _ in range(5):
        statement = client.get(
            f"/api/consultations/{consultation_id}/statements/next",
            params={"session_token": session_token},
        ).json()
        assert statement["id"] not in seen
        seen.add(statement["id"])
        client.post(
            f"/api/consultations/{consultation_id}/votes",
            json={"session_token": session_token, "statement_id": statement["id"], "value": 1},
        )
