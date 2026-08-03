"""Tests for the SQLModel schema."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from sabha.models import Consultation, Participant, Statement, Vote

EXPECTED_TABLES = {
    "consultation",
    "statement",
    "participant",
    "vote",
    "modelrun",
    "clause",
    "clausestatementlink",
    "filing",
    "filingclauselink",
    "reply",
    "ledgerentry",
}


def test_schema_creates_cleanly() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    assert EXPECTED_TABLES.issubset(set(SQLModel.metadata.tables.keys()))


def test_vote_is_unique_per_participant_and_statement() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(UTC)

    with Session(engine) as session:
        consultation = Consultation(title="t", question="q", opens_at=now, closes_at=now)
        session.add(consultation)
        session.flush()
        assert consultation.id is not None

        statement = Statement(
            consultation_id=consultation.id, code="S-0001", text="x", language="en"
        )
        participant = Participant(consultation_id=consultation.id, session_token="p1")
        session.add(statement)
        session.add(participant)
        session.flush()
        assert statement.id is not None
        assert participant.id is not None

        session.add(Vote(participant_id=participant.id, statement_id=statement.id, value=1))
        session.commit()

        session.add(Vote(participant_id=participant.id, statement_id=statement.id, value=-1))
        with pytest.raises(IntegrityError):
            session.commit()
