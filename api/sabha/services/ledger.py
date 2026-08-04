"""The append-only accountability ledger.

Every autonomous action this system takes against a public institution,
filing a clause set, deferring one for a human gate, escalating a
filing, holding an escalation back on a rate limit, is written here
with the policy state that produced it. Section 9 of the project
description: the ledger is the public record an outsider audits, so
nothing in this module ever updates or deletes a row, it only appends.
"""

from typing import Any

from sqlmodel import Session, col, select

from sabha.models import LedgerEntry


def record(
    session: Session,
    *,
    action: str,
    reason: str,
    policy_state: dict[str, Any],
    filing_id: int | None = None,
    consultation_id: int | None = None,
) -> LedgerEntry:
    """Append one entry and return it, refreshed with its id and timestamp."""
    entry = LedgerEntry(
        action=action,
        reason=reason,
        policy_state=policy_state,
        filing_id=filing_id,
        consultation_id=consultation_id,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def ledger_for_consultation(session: Session, consultation_id: int) -> list[LedgerEntry]:
    """Every entry for this consultation, oldest first, the order a reader
    of the public record expects.
    """
    return list(
        session.exec(
            select(LedgerEntry)
            .where(LedgerEntry.consultation_id == consultation_id)
            .order_by(col(LedgerEntry.occurred_at).asc(), col(LedgerEntry.id).asc())
        ).all()
    )


def ledger_for_filing(session: Session, filing_id: int) -> list[LedgerEntry]:
    """Every entry recorded against one filing, oldest first: the full
    history of what the escalation scheduler and the filing adapter did
    to it.
    """
    return list(
        session.exec(
            select(LedgerEntry)
            .where(LedgerEntry.filing_id == filing_id)
            .order_by(col(LedgerEntry.occurred_at).asc(), col(LedgerEntry.id).asc())
        ).all()
    )
