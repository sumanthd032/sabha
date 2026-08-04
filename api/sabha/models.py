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


class LlmCache(SQLModel, table=True):
    """A cached language model response, keyed on sha256(model + prompt + schema).

    Checked before every call in llm/client.py, so a development rerun of
    the same generation, drafting, routing, or evaluation prompt costs
    zero requests against the free tier's daily budget.
    """

    id: int | None = Field(default=None, primary_key=True)
    cache_key: str = Field(unique=True, index=True)
    model: str
    schema_name: str
    prompt: str
    response_json: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)


class EmbeddingCache(SQLModel, table=True):
    """A cached embedding vector, keyed on sha256(model + content).

    Any given piece of text is embedded once, ever: a repeat request for
    the same text under the same model reads this row instead of calling
    the API again.
    """

    id: int | None = Field(default=None, primary_key=True)
    content_hash: str = Field(unique=True, index=True)
    model: str
    vector: list[float] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)


class QuotaUsage(SQLModel, table=True):
    """A persisted per-day request counter for the Gemini free tier guard.

    The per-minute half of the guard is a token bucket held in process
    memory, since a minute's window resets on its own regardless of
    restarts. The per-day half has to survive a restart within the same
    day, which is what this table is for.
    """

    id: int | None = Field(default=None, primary_key=True)
    day: str = Field(unique=True, index=True)
    request_count: int = Field(default=0)


class AllocationRule(SQLModel, table=True):
    """One indexed entry from the Allocation of Business Rules.

    embedding is computed once, when the rule set is loaded, and reused
    for every routing decision rather than recomputed per request.
    """

    id: int | None = Field(default=None, primary_key=True)
    department: str
    citation: str
    mandate_text: str
    embedding: list[float] = Field(sa_column=Column(JSON))


class RoutingDecision(SQLModel, table=True):
    """A jurisdiction routing decision for one drafted clause, against one
    candidate department.

    Multi label by construction: a clause can and often does receive more
    than one row, one per department whose mandate plausibly covers it.
    needs_human_review is set whenever this row's own confidence is low,
    per section 6.5: a low confidence route is queued for a human rather
    than filed on a guess, even if other rows for the same clause are
    confident.
    """

    id: int | None = Field(default=None, primary_key=True)
    clause_id: int = Field(foreign_key="clause.id")
    allocation_rule_id: int = Field(foreign_key="allocationrule.id")
    department: str
    citation: str
    confidence: float
    rationale: str
    needs_human_review: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)
