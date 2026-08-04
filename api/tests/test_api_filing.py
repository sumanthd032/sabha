"""API level tests for filing a clause set, recording a reply, the
manual escalation sweep, and the ledger's public read view.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from sabha.models import Clause, Consultation

DEPARTMENT = "Ministry of Labour and Employment"


def _seed_consultation_and_clause(test_engine: Engine) -> tuple[int, int]:
    with Session(test_engine) as session:
        consultation = Consultation(
            title="Platform work regulation",
            question="Should platform workers be classed as employees?",
            is_synthetic=True,
            opens_at=datetime.now(UTC),
            closes_at=datetime.now(UTC),
        )
        session.add(consultation)
        session.commit()
        session.refresh(consultation)
        assert consultation.id is not None

        clause = Clause(
            consultation_id=consultation.id, model_run_id=1,
            text="Platforms shall register with the ministry.", certificate_figures={},
        )
        session.add(clause)
        session.commit()
        session.refresh(clause)
        assert clause.id is not None
        return consultation.id, clause.id


def test_create_filing_requires_confirmation_for_a_new_department(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id, clause_id = _seed_consultation_and_clause(test_engine)

    response = client.post(
        f"/api/consultations/{consultation_id}/filings",
        json={"department": DEPARTMENT, "clause_ids": [clause_id]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["department"] == DEPARTMENT


def test_create_filing_succeeds_with_confirmation_and_appears_in_the_list(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id, clause_id = _seed_consultation_and_clause(test_engine)

    response = client.post(
        f"/api/consultations/{consultation_id}/filings",
        json={
            "department": DEPARTMENT, "clause_ids": [clause_id],
            "confirmed_new_department": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "filed"
    assert body["department"] == DEPARTMENT

    listed = client.get(f"/api/consultations/{consultation_id}/filings").json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_reply_stops_the_clock(client: TestClient, test_engine: Engine) -> None:
    consultation_id, clause_id = _seed_consultation_and_clause(test_engine)
    filing = client.post(
        f"/api/consultations/{consultation_id}/filings",
        json={
            "department": DEPARTMENT, "clause_ids": [clause_id],
            "confirmed_new_department": True,
        },
    ).json()

    response = client.post(
        f"/api/consultations/{consultation_id}/filings/{filing['id']}/replies",
        json={"received_text": "we have reviewed the submission and taken note"},
    )

    assert response.status_code == 200
    listed = client.get(f"/api/consultations/{consultation_id}/filings").json()
    assert listed[0]["stage"] == "replied"


def test_ledger_records_the_filing(client: TestClient, test_engine: Engine) -> None:
    consultation_id, clause_id = _seed_consultation_and_clause(test_engine)
    client.post(
        f"/api/consultations/{consultation_id}/filings",
        json={
            "department": DEPARTMENT, "clause_ids": [clause_id],
            "confirmed_new_department": True,
        },
    )

    ledger = client.get(f"/api/consultations/{consultation_id}/ledger").json()

    actions = [entry["action"] for entry in ledger["entries"]]
    assert "filing_submitted" in actions


def test_escalation_sweep_starts_the_clock(client: TestClient, test_engine: Engine) -> None:
    consultation_id, clause_id = _seed_consultation_and_clause(test_engine)
    client.post(
        f"/api/consultations/{consultation_id}/filings",
        json={
            "department": DEPARTMENT, "clause_ids": [clause_id],
            "confirmed_new_department": True,
        },
    )

    response = client.post("/api/escalation/sweep")

    assert response.status_code == 200
    updated = response.json()
    assert len(updated) == 1
    assert updated[0]["stage"] == "awaiting_reply"
