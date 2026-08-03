"""Request and response shapes for the REST and WebSocket API.

Kept separate from models.py: the database tables carry columns an API
consumer has no business seeing, such as a synthetic participant's
planted factor, and a response shape carries joined, display ready
fields, such as a statement's code alongside its ranking figure, that no
table stores directly.
"""

from datetime import datetime
from typing import Literal

from sqlmodel import SQLModel

from sabha.models import AuthorType


class ConsultationOut(SQLModel):
    id: int
    title: str
    question: str
    department: str | None
    is_synthetic: bool
    opens_at: datetime
    closes_at: datetime


class StatementOut(SQLModel):
    id: int
    code: str
    text: str
    language: str
    author_type: AuthorType
    parent_statement_id: int | None
    is_synthetic: bool


class JoinResponse(SQLModel):
    participant_id: int
    session_token: str


class VoteRequest(SQLModel):
    session_token: str
    statement_id: int
    value: Literal[-1, 1]


class VoteResponse(SQLModel):
    id: int
    statement_id: int
    value: int
    created_at: datetime


class RankingEntry(SQLModel):
    statement_id: int
    code: str
    text: str
    score: float
    rank: int


class RankingsOut(SQLModel):
    model_run_id: int | None
    model_run_created_at: datetime | None
    bridging: list[RankingEntry]
    majority: list[RankingEntry]


class ModelRunOut(SQLModel):
    id: int
    consultation_id: int
    k_clusters: int
    created_at: datetime
    participant_count: int
    statement_count: int


class OpinionMapPoint(SQLModel):
    participant_id: int
    factor: tuple[float, float]
    cluster: int
    is_self: bool


class OpinionMapOut(SQLModel):
    model_run_id: int
    k_clusters: int
    points: list[OpinionMapPoint]


class ClusterSupportOut(SQLModel):
    cluster: int
    participant_count: int
    agree_count: int
    agree_fraction: float


class CertificateOut(SQLModel):
    model_run_id: int
    statement: StatementOut
    participant_count: int
    clusters: list[ClusterSupportOut]
