"""Tests for the filing adapter: channel resolution, the human gate,
document rendering, and filing persistence.
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from sabha.models import Clause, ClauseStatementLink, Filing, FilingStage, Statement
from sabha.services.filing import (
    HumanGateRequiredError,
    LiveFilingNotConfiguredError,
    MockFilingChannel,
    department_has_prior_filing,
    file_clause_set,
    record_reply,
    render_filing_document,
    resolve_channel,
)
from sabha.services.ledger import ledger_for_consultation

DEPARTMENT = "Ministry of Labour and Employment"


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _clause(session: Session, text: str = "a clause") -> Clause:
    clause = Clause(consultation_id=1, model_run_id=1, text=text, certificate_figures={})
    session.add(clause)
    session.commit()
    session.refresh(clause)
    return clause


def _statement(session: Session, code: str) -> Statement:
    statement = Statement(consultation_id=1, code=code, text="statement text", language="en")
    session.add(statement)
    session.commit()
    session.refresh(statement)
    return statement


def test_resolve_channel_returns_mock_by_default() -> None:
    channel = resolve_channel("mock", "")
    assert isinstance(channel, MockFilingChannel)


def test_resolve_channel_raises_without_the_confirmation_phrase() -> None:
    with pytest.raises(LiveFilingNotConfiguredError):
        resolve_channel("live", "")


def test_resolve_channel_raises_even_with_the_confirmation_phrase() -> None:
    """Section 9: no configuration reaches a live channel, since this
    build implements none.
    """
    with pytest.raises(LiveFilingNotConfiguredError):
        resolve_channel("live", "i-confirm-this-points-at-a-real-government-endpoint")


def test_file_clause_set_blocks_a_first_filing_without_confirmation() -> None:
    with _fresh_session() as session:
        clause = _clause(session)
        assert clause.id is not None
        channel = MockFilingChannel()

        with pytest.raises(HumanGateRequiredError) as excinfo:
            file_clause_set(session, 1, DEPARTMENT, [clause.id], channel)
        assert excinfo.value.department == DEPARTMENT

        assert session.exec(select(Filing)).all() == []
        entries = ledger_for_consultation(session, 1)
        assert entries[-1].action == "filing_blocked_pending_human_gate"


def test_file_clause_set_succeeds_with_confirmation_and_persists_links() -> None:
    with _fresh_session() as session:
        clause = _clause(session)
        assert clause.id is not None
        statement = _statement(session, "S-0001")
        session.add(ClauseStatementLink(clause_id=clause.id, statement_id=statement.id))
        session.commit()
        channel = MockFilingChannel()

        filing = file_clause_set(
            session, 1, DEPARTMENT, [clause.id], channel, confirmed_new_department=True
        )

        assert filing.stage == FilingStage.FILED
        assert filing.artefact == f"MOCK-{filing.id:06d}"
        assert filing.statutory_deadline is not None

        entries = ledger_for_consultation(session, 1)
        assert entries[-1].action == "filing_submitted"


def test_a_second_filing_to_the_same_department_needs_no_confirmation() -> None:
    with _fresh_session() as session:
        clause = _clause(session)
        assert clause.id is not None
        channel = MockFilingChannel()
        file_clause_set(session, 1, DEPARTMENT, [clause.id], channel, confirmed_new_department=True)
        assert department_has_prior_filing(session, DEPARTMENT) is True

        second_clause = _clause(session, "a second clause")
        assert second_clause.id is not None
        filing = file_clause_set(session, 1, DEPARTMENT, [second_clause.id], channel)

        assert filing.stage == FilingStage.FILED


def test_render_filing_document_includes_clause_text_and_statement_codes() -> None:
    with _fresh_session() as session:
        clause = _clause(session, "Platforms shall pay into a welfare fund.")
        statement = _statement(session, "S-0012")
        session.add(ClauseStatementLink(clause_id=clause.id, statement_id=statement.id))
        session.commit()

        document = render_filing_document(session, DEPARTMENT, [clause])

        assert DEPARTMENT in document
        assert "S-0012" in document
        assert "welfare fund" in document


def test_record_reply_stops_the_clock() -> None:
    with _fresh_session() as session:
        clause = _clause(session)
        assert clause.id is not None
        channel = MockFilingChannel()
        filing = file_clause_set(
            session, 1, DEPARTMENT, [clause.id], channel, confirmed_new_department=True
        )

        reply = record_reply(session, filing, "we have reviewed the submission")

        session.refresh(filing)
        assert filing.stage == FilingStage.REPLIED
        assert reply.filing_id == filing.id
        entries = ledger_for_consultation(session, 1)
        assert entries[-1].action == "reply_received"
