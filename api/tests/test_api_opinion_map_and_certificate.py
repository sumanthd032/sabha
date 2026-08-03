"""Tests for the opinion map and consensus certificate endpoints."""

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from sabha.seed.loader import load_seed
from sabha.services.factorisation import FactorisationParams
from sabha.services.model_run import fit_and_persist


def _seed_consultation_with_an_existing_fit(engine: Engine, num_participants: int = 150) -> int:
    with Session(engine) as session:
        load_seed(session, num_participants=num_participants, seed=9)
        model_run = fit_and_persist(session, consultation_id=1, params=FactorisationParams())
        assert model_run.id is not None
    return 1


def test_opinion_map_before_any_model_run_is_404(client: TestClient, test_engine: Engine) -> None:
    with Session(test_engine) as session:
        load_seed(session, num_participants=20, seed=1)

    assert client.get("/api/consultations/1/opinion-map").status_code == 404
    assert client.get("/api/consultations/1/certificate").status_code == 404


def test_opinion_map_returns_one_point_per_participant(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_consultation_with_an_existing_fit(test_engine, num_participants=150)

    response = client.get(f"/api/consultations/{consultation_id}/opinion-map")
    assert response.status_code == 200
    body = response.json()

    assert body["model_run_id"] is not None
    assert body["k_clusters"] >= 2
    assert len(body["points"]) == 150
    assert all(len(point["factor"]) == 2 for point in body["points"])
    assert all(point["is_self"] is False for point in body["points"])


def test_opinion_map_marks_the_requesting_participant_as_self(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_consultation_with_an_existing_fit(test_engine)

    join_response = client.post(f"/api/consultations/{consultation_id}/join")
    session_token = join_response.json()["session_token"]
    participant_id = join_response.json()["participant_id"]

    with Session(test_engine) as session:
        fit_and_persist(session, consultation_id, FactorisationParams())

    response = client.get(
        f"/api/consultations/{consultation_id}/opinion-map",
        params={"session_token": session_token},
    )
    assert response.status_code == 200
    points = response.json()["points"]

    self_points = [p for p in points if p["is_self"]]
    assert len(self_points) == 1
    assert self_points[0]["participant_id"] == participant_id


def test_certificate_covers_the_top_bridging_statement(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_consultation_with_an_existing_fit(test_engine)

    rankings = client.get(f"/api/consultations/{consultation_id}/rankings").json()
    top_bridging_statement_id = rankings["bridging"][0]["statement_id"]

    response = client.get(f"/api/consultations/{consultation_id}/certificate")
    assert response.status_code == 200
    body = response.json()

    assert body["statement"]["id"] == top_bridging_statement_id
    assert body["participant_count"] > 0
    assert len(body["clusters"]) >= 2
    assert sum(c["participant_count"] for c in body["clusters"]) == body["participant_count"]
    for cluster in body["clusters"]:
        assert 0.0 <= cluster["agree_fraction"] <= 1.0
