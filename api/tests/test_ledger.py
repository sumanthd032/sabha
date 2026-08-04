"""Tests for the append-only ledger: recording and reading entries
back in the order a public reader expects.
"""

from sqlmodel import Session, SQLModel, create_engine

from sabha.services.ledger import ledger_for_consultation, ledger_for_filing, record


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_record_persists_and_returns_the_entry() -> None:
    with _fresh_session() as session:
        entry = record(
            session, action="filing_submitted", reason="because", policy_state={"a": 1},
            consultation_id=1,
        )

        assert entry.id is not None
        assert entry.action == "filing_submitted"
        assert entry.policy_state == {"a": 1}


def test_ledger_for_consultation_returns_entries_oldest_first() -> None:
    with _fresh_session() as session:
        record(session, action="first", reason="r1", policy_state={}, consultation_id=1)
        record(session, action="second", reason="r2", policy_state={}, consultation_id=1)
        record(session, action="unrelated", reason="r3", policy_state={}, consultation_id=2)

        entries = ledger_for_consultation(session, 1)

        assert [entry.action for entry in entries] == ["first", "second"]


def test_ledger_for_filing_returns_only_that_filings_entries() -> None:
    with _fresh_session() as session:
        record(session, action="a", reason="r", policy_state={}, filing_id=1, consultation_id=1)
        record(session, action="b", reason="r", policy_state={}, filing_id=2, consultation_id=1)

        entries = ledger_for_filing(session, 1)

        assert [entry.action for entry in entries] == ["a"]
