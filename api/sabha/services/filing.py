"""The filing adapter: one channel interface, one sandboxed implementation.

Section 9 of the project description sets three constraints that shape
every function here. First, the adapter is sandboxed by default and
this build ships no other channel: resolve_channel raises for any
filing_mode other than "mock", and raises again even when a caller
supplies the live confirmation phrase, because there is no
LiveFilingChannel class to hand back. A future build that genuinely
wants a live channel has to write one and delete that second raise
deliberately, which is the point: no environment variable alone can
make this code file anywhere but the sandbox. Second, a human gate
sits in front of the first filing to any department this consultation
has not filed to before, enforced in file_clause_set rather than left
to a caller's discipline. Third, every filing and every gate decision
is written to the ledger with the policy state behind it.

The channel dispatches a rendered document and gets back a reference
string, which is all Filing.artefact stores; the document itself is
reconstructed on demand by render_filing_document rather than kept
twice, the same reasoning that keeps a clause's statement_ids off the
Clause row itself.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlmodel import Session, col, select

from sabha.models import (
    Clause,
    ClauseStatementLink,
    Filing,
    FilingClauseLink,
    FilingStage,
    Reply,
    Statement,
)
from sabha.services.ledger import record

_LIVE_CONFIRMATION_PHRASE = "i-confirm-this-points-at-a-real-government-endpoint"


class LiveFilingNotConfiguredError(Exception):
    """Raised for any filing_mode other than mock. This build has no live
    channel to resolve to regardless of confirmation, per section 9.
    """


class HumanGateRequiredError(Exception):
    """Raised when a filing targets a department this consultation has
    never filed to before and the caller has not passed
    confirmed_new_department, section 9's human gate.
    """

    def __init__(self, department: str) -> None:
        self.department = department
        super().__init__(f"filing to a new department requires human confirmation: {department}")


class FilingChannel(Protocol):
    """One department facing submission channel."""

    name: str

    def submit(self, filing_id: int, document_text: str) -> str:
        """Dispatch the rendered document and return an artefact reference."""


@dataclass
class MockFilingChannel:
    """The only channel this build ships. It fabricates a deterministic
    reference from the filing's own id and reaches no network, since
    the build never files anywhere but the sandbox.
    """

    name: str = "mock"
    reply_window_days: int = 30

    def submit(self, filing_id: int, document_text: str) -> str:
        return f"MOCK-{filing_id:06d}"


def resolve_channel(filing_mode: str, live_confirmation: str) -> FilingChannel:
    """The channel this build's config resolves to, per section 9.

    filing_mode "mock" is the only path that returns anything. Anything
    else raises, with a different message depending on whether the
    confirmation phrase was also supplied, so an operator who tries to
    go live learns from the error that the phrase was not the missing
    piece, a channel class is.
    """
    if filing_mode == "mock":
        return MockFilingChannel()
    if live_confirmation != _LIVE_CONFIRMATION_PHRASE:
        raise LiveFilingNotConfiguredError(
            f"filing_mode {filing_mode!r} also requires FILING_LIVE_CONFIRMATION "
            "set to the exact confirmation phrase before it is even considered"
        )
    raise LiveFilingNotConfiguredError(
        f"filing_mode {filing_mode!r} confirmed, but this build implements no live "
        "filing channel; only mock ships in this codebase"
    )


def department_has_prior_filing(session: Session, department: str) -> bool:
    """Whether this department has ever received a filing before, the
    fact the human gate is checking.
    """
    existing = session.exec(select(Filing).where(Filing.department == department)).first()
    return existing is not None


def _clause_statement_codes(session: Session, clause_id: int) -> list[str]:
    statement_ids = session.exec(
        select(ClauseStatementLink.statement_id).where(
            ClauseStatementLink.clause_id == clause_id
        )
    ).all()
    if not statement_ids:
        return []
    codes = session.exec(
        select(Statement.code).where(col(Statement.id).in_(statement_ids))
    ).all()
    return sorted(codes)


def render_filing_document(session: Session, department: str, clauses: list[Clause]) -> str:
    """The human readable submission text a channel dispatches.

    Reconstructed on demand from the clauses and their linked
    statements, rather than stored a second time on the Filing row,
    the same reasoning that keeps a clause's own statement_ids off the
    Clause table.
    """
    sections = []
    for clause in clauses:
        assert clause.id is not None
        codes = _clause_statement_codes(session, clause.id)
        codes_line = ", ".join(codes) if codes else "no linked statements"
        sections.append(f"Clause (statements {codes_line}):\n{clause.text}")
    body = "\n\n".join(sections)
    return f"Filing to: {department}\n\n{body}"


@dataclass(frozen=True)
class FilingParams:
    reply_window_days: int = 30


def file_clause_set(
    session: Session,
    consultation_id: int,
    department: str,
    clause_ids: list[int],
    channel: FilingChannel,
    confirmed_new_department: bool = False,
    params: FilingParams | None = None,
    now: datetime | None = None,
) -> Filing:
    """File the given clauses to department through channel.

    Raises HumanGateRequiredError, and records the attempt on the
    ledger without ever writing a Filing row, when this is the first
    filing to department and the caller has not passed
    confirmed_new_department. Section 9: a human confirms before the
    system files to a department it has never filed to, every time.
    """
    params = params or FilingParams()
    now = now or datetime.now(UTC)

    if not department_has_prior_filing(session, department) and not confirmed_new_department:
        record(
            session,
            action="filing_blocked_pending_human_gate",
            reason=f"first filing to {department} requires human confirmation",
            policy_state={"department": department, "clause_ids": clause_ids},
            consultation_id=consultation_id,
        )
        raise HumanGateRequiredError(department)

    clauses = list(session.exec(select(Clause).where(col(Clause.id).in_(clause_ids))).all())
    document_text = render_filing_document(session, department, clauses)

    filing = Filing(
        consultation_id=consultation_id,
        department=department,
        channel=channel.name,
        artefact="",
        stage=FilingStage.DRAFTED,
    )
    session.add(filing)
    session.flush()
    assert filing.id is not None
    for clause in clauses:
        assert clause.id is not None
        session.add(FilingClauseLink(filing_id=filing.id, clause_id=clause.id))

    reference = channel.submit(filing.id, document_text)
    filing.artefact = reference
    filing.stage = FilingStage.FILED
    filing.submitted_at = now
    filing.statutory_deadline = now + timedelta(days=params.reply_window_days)
    session.add(filing)
    session.commit()
    session.refresh(filing)

    record(
        session,
        action="filing_submitted",
        reason=f"filed {len(clause_ids)} clause(s) to {department} via {channel.name}",
        policy_state={
            "channel": channel.name,
            "clause_ids": clause_ids,
            "artefact": reference,
            "statutory_deadline": filing.statutory_deadline.isoformat(),
        },
        filing_id=filing.id,
        consultation_id=consultation_id,
    )
    return filing


def record_reply(session: Session, filing: Filing, received_text: str) -> Reply:
    """Record a department's reply and stop this filing's escalation
    clock. The only path in this codebase that creates a Reply row, so
    services/reply_evaluation.py always has provenance to score
    against.
    """
    assert filing.id is not None
    reply = Reply(filing_id=filing.id, received_text=received_text)
    session.add(reply)
    filing.stage = FilingStage.REPLIED
    session.add(filing)
    session.commit()
    session.refresh(reply)
    session.refresh(filing)

    record(
        session,
        action="reply_received",
        reason=f"{filing.department} replied to filing {filing.id}",
        policy_state={"filing_id": filing.id},
        filing_id=filing.id,
        consultation_id=filing.consultation_id,
    )
    return reply
