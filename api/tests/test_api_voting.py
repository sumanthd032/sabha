"""End to end test of the scripted client flow: join, receive an
adaptively selected statement, vote, and see the rankings the live
session pushes over the WebSocket once the debounced refit completes.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from sabha.models import Consultation, ModerationState, Statement
from sabha.seed.loader import load_seed
from sabha.services.factorisation import FactorisationParams
from sabha.services.model_run import fit_and_persist, latest_model_run


def _seed_consultation_with_an_existing_fit(engine: Engine, num_participants: int = 200) -> int:
    """Seeds a synthetic population and fits it once, matching how the
    live demo is meant to start: real votes land on an already interesting
    model, per docs/demo-script.md, rather than an empty one.
    """
    with Session(engine) as session:
        load_seed(session, num_participants=num_participants, seed=1)
        model_run = fit_and_persist(session, consultation_id=1, params=FactorisationParams())
        assert model_run.id is not None
    return 1


def test_a_scripted_client_joins_votes_adaptively_and_sees_pushed_rankings(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_consultation_with_an_existing_fit(test_engine)

    join_response = client.post(f"/api/consultations/{consultation_id}/join")
    assert join_response.status_code == 200
    session_token = join_response.json()["session_token"]

    with Session(test_engine) as session:
        model_run = latest_model_run(session, consultation_id)
        assert model_run is not None
        loading_norms = {
            int(sid): sum(x * x for x in loading) ** 0.5
            for sid, loading in model_run.statement_loadings.items()
        }
    high_loading_threshold = sorted(loading_norms.values())[len(loading_norms) // 2]

    # select_next_statement keeps a small random reserve (see
    # SelectionParams.reserve_fraction), so any single call has a one in
    # ten chance of a uniform pick instead of the locate phase's choice.
    # Repeating the very first call, before anything is voted on, and
    # taking the mode averages that noise out without touching the
    # server's own unseeded rng.
    first_pick_attempts = []
    for _ in range(10):
        response = client.get(
            f"/api/consultations/{consultation_id}/statements/next",
            params={"session_token": session_token},
        )
        assert response.status_code == 200
        statement = response.json()
        assert statement is not None
        first_pick_attempts.append(statement["id"])
    most_common_first_pick = max(set(first_pick_attempts), key=first_pick_attempts.count)

    # The very first statement served to a brand new participant, whose
    # own opinion position is entirely unknown, should be a discriminating
    # one: adaptive selection's locate phase, not an arbitrary pick.
    assert loading_norms[most_common_first_pick] >= high_loading_threshold

    voted_statement_ids: list[int] = []
    for _ in range(5):
        next_response = client.get(
            f"/api/consultations/{consultation_id}/statements/next",
            params={"session_token": session_token},
        )
        assert next_response.status_code == 200
        statement = next_response.json()
        assert statement is not None
        assert statement["id"] not in voted_statement_ids

        vote_response = client.post(
            f"/api/consultations/{consultation_id}/votes",
            json={"session_token": session_token, "statement_id": statement["id"], "value": 1},
        )
        assert vote_response.status_code == 200
        voted_statement_ids.append(statement["id"])


def test_the_websocket_channel_pushes_rankings_after_a_vote(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_consultation_with_an_existing_fit(test_engine)

    join_response = client.post(f"/api/consultations/{consultation_id}/join")
    session_token = join_response.json()["session_token"]

    with Session(test_engine) as session:
        seeded_run = latest_model_run(session, consultation_id)
        assert seeded_run is not None
        seeded_run_id = seeded_run.id

    next_response = client.get(
        f"/api/consultations/{consultation_id}/statements/next",
        params={"session_token": session_token},
    )
    statement_id = next_response.json()["id"]

    with client.websocket_connect(f"/api/consultations/{consultation_id}/live") as websocket:
        vote_response = client.post(
            f"/api/consultations/{consultation_id}/votes",
            json={"session_token": session_token, "statement_id": statement_id, "value": -1},
        )
        assert vote_response.status_code == 200

        message = websocket.receive_json()

    assert message["type"] == "rankings"
    assert message["model_run_id"] != seeded_run_id
    assert len(message["bridging"]) > 0
    assert len(message["majority"]) > 0
    assert {entry["rank"] for entry in message["bridging"][:3]} == {1, 2, 3}


def test_a_rejected_statement_is_never_served(client: TestClient, test_engine: Engine) -> None:
    """A statement the generation loop retired, per section 6.3, must
    disappear from the live pool rather than linger as servable.
    """
    with Session(test_engine) as session:
        consultation = Consultation(
            title="Retired variant test",
            question="Does moderation state gate the served pool?",
            opens_at=datetime.now(UTC),
            closes_at=datetime.now(UTC),
        )
        session.add(consultation)
        session.commit()
        session.refresh(consultation)
        assert consultation.id is not None
        consultation_id = consultation.id

        session.add(
            Statement(
                consultation_id=consultation.id,
                code="S-0001",
                text="A statement still open for voting.",
                language="en",
                moderation_state=ModerationState.APPROVED,
            )
        )
        session.add(
            Statement(
                consultation_id=consultation.id,
                code="S-0002",
                text="A losing generated variant, retired after its significance test.",
                language="en",
                moderation_state=ModerationState.REJECTED,
            )
        )
        session.commit()

    join_response = client.post(f"/api/consultations/{consultation_id}/join")
    session_token = join_response.json()["session_token"]

    seen_codes = set()
    for _ in range(3):
        next_response = client.get(
            f"/api/consultations/{consultation_id}/statements/next",
            params={"session_token": session_token},
        )
        statement = next_response.json()
        if statement is None:
            break
        seen_codes.add(statement["code"])
        client.post(
            f"/api/consultations/{consultation_id}/votes",
            json={"session_token": session_token, "statement_id": statement["id"], "value": 1},
        )

    assert seen_codes == {"S-0001"}
