"""Every persisted entity in Sabha, as SQLModel tables.

Votes are never updated once cast, and model runs are inserted as new
snapshots rather than updated in place, so that a figure shown to the
public on one day can be reproduced exactly on another. Nothing in this
module enforces that at the database level beyond the natural absence of
an update path in the services and routers built on top of it; it is a
convention every later step must keep.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuthorType(StrEnum):
    """Who put a statement's text into the pool."""

    PARTICIPANT = "participant"
    GENERATED = "generated"


class ModerationState(StrEnum):
    """Whether a statement is visible in the live voting pool."""

    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"


class FilingStage(StrEnum):
    """Where a filing sits in the statutory reply and escalation clock."""

    DRAFTED = "drafted"
    FILED = "filed"
    AWAITING_REPLY = "awaiting_reply"
    ESCALATED_APPELLATE = "escalated_appellate"
    ESCALATED_COMMISSION = "escalated_commission"
    REPLIED = "replied"
    CLOSED = "closed"


class Consultation(SQLModel, table=True):
    """The draft rule or question under discussion."""

    id: int | None = Field(default=None, primary_key=True)
    title: str
    question: str
    department: str | None = Field(default=None)
    is_synthetic: bool = Field(default=False)
    opens_at: datetime
    closes_at: datetime
    created_at: datetime = Field(default_factory=_utcnow)

    statements: list["Statement"] = Relationship(back_populates="consultation")
    participants: list["Participant"] = Relationship(back_populates="consultation")


class Statement(SQLModel, table=True):
    """A short statement participants vote on.

    parent_statement_id is set only when author_type is generated, and
    points at the statement a generation loop run proposed a reformulation
    of. is_synthetic marks seed corpus statements manufactured for this
    build rather than collected from real submissions.
    """

    id: int | None = Field(default=None, primary_key=True)
    consultation_id: int = Field(foreign_key="consultation.id")
    code: str = Field(unique=True, index=True)
    text: str
    language: str
    author_type: AuthorType = Field(default=AuthorType.PARTICIPANT)
    parent_statement_id: int | None = Field(default=None, foreign_key="statement.id")
    moderation_state: ModerationState = Field(default=ModerationState.APPROVED)
    is_synthetic: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)

    consultation: Consultation = Relationship(back_populates="statements")


class Participant(SQLModel, table=True):
    """An anonymous session identity.

    planted_factor and planted_cluster hold the ground truth latent
    position used to generate a synthetic participant's votes, so a test
    can check that fitting the model recovers what was planted. They are
    always null for a real participant.
    """

    id: int | None = Field(default=None, primary_key=True)
    consultation_id: int = Field(foreign_key="consultation.id")
    session_token: str = Field(unique=True, index=True)
    factor_vector: list[float] | None = Field(default=None, sa_column=Column(JSON))
    weight: float = Field(default=1.0)
    is_synthetic: bool = Field(default=False)
    planted_factor: list[float] | None = Field(default=None, sa_column=Column(JSON))
    planted_cluster: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)

    consultation: Consultation = Relationship(back_populates="participants")


class Vote(SQLModel, table=True):
    """An immutable participant vote on a statement.

    +1 for agree, -1 for disagree. A pass or an unseen statement is
    simply the absence of a row, never a stored value, so the
    factorisation model's "observed entries only" loss needs no sentinel.
    There is deliberately no update endpoint anywhere in this codebase:
    once a row is inserted it is never changed.
    """

    __table_args__ = (UniqueConstraint("participant_id", "statement_id"),)

    id: int | None = Field(default=None, primary_key=True)
    participant_id: int = Field(foreign_key="participant.id")
    statement_id: int = Field(foreign_key="statement.id")
    value: int
    created_at: datetime = Field(default_factory=_utcnow)


class ModelRun(SQLModel, table=True):
    """A fitted snapshot of the bridging factorisation model.

    Inserted fresh on every refit, never updated, so a figure shown to
    the public can be reproduced exactly by loading the run it came from.
    """

    id: int | None = Field(default=None, primary_key=True)
    consultation_id: int = Field(foreign_key="consultation.id")
    params: dict[str, Any] = Field(sa_column=Column(JSON))
    statement_intercepts: dict[str, float] = Field(sa_column=Column(JSON))
    participant_factors: dict[str, list[float]] = Field(sa_column=Column(JSON))
    statement_loadings: dict[str, list[float]] = Field(sa_column=Column(JSON))
    participant_biases: dict[str, float] = Field(sa_column=Column(JSON))
    cluster_assignments: dict[str, int] = Field(sa_column=Column(JSON))
    k_clusters: int
    created_at: datetime = Field(default_factory=_utcnow)


class ClauseStatementLink(SQLModel, table=True):
    """Which statements a drafted clause carries as its support."""

    clause_id: int | None = Field(default=None, foreign_key="clause.id", primary_key=True)
    statement_id: int | None = Field(default=None, foreign_key="statement.id", primary_key=True)


class Clause(SQLModel, table=True):
    """Drafted clause text with the consensus certificate figures behind it."""

    id: int | None = Field(default=None, primary_key=True)
    consultation_id: int = Field(foreign_key="consultation.id")
    model_run_id: int = Field(foreign_key="modelrun.id")
    text: str
    certificate_figures: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)


class FilingClauseLink(SQLModel, table=True):
    """Which clauses a filing bundles into one consolidated submission."""

    filing_id: int | None = Field(default=None, foreign_key="filing.id", primary_key=True)
    clause_id: int | None = Field(default=None, foreign_key="clause.id", primary_key=True)


class Filing(SQLModel, table=True):
    """A clause set submitted to a department through one channel."""

    id: int | None = Field(default=None, primary_key=True)
    consultation_id: int = Field(foreign_key="consultation.id")
    department: str
    channel: str
    artefact: str
    stage: FilingStage = Field(default=FilingStage.DRAFTED)
    submitted_at: datetime | None = Field(default=None)
    statutory_deadline: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)


class Reply(SQLModel, table=True):
    """A department's reply to a filing, scored for substance."""

    id: int | None = Field(default=None, primary_key=True)
    filing_id: int = Field(foreign_key="filing.id")
    received_text: str
    engagement_score: float | None = Field(default=None)
    template_cluster: str | None = Field(default=None)
    received_at: datetime = Field(default_factory=_utcnow)


class LedgerEntry(SQLModel, table=True):
    """An append-only record of one autonomous action and the policy behind it."""

    id: int | None = Field(default=None, primary_key=True)
    occurred_at: datetime = Field(default_factory=_utcnow)
    action: str
    reason: str
    policy_state: dict[str, Any] = Field(sa_column=Column(JSON))
    filing_id: int | None = Field(default=None, foreign_key="filing.id")
    consultation_id: int | None = Field(default=None, foreign_key="consultation.id")
