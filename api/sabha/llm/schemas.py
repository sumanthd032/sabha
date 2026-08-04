"""Structured output shapes for every language model call.

Every schema wraps its list in a named object field rather than asking
for a bare array back: response_json_schema needs one top level object,
and a batch of N results in a single field is what section 4.2 means by
one request returning N variants rather than N requests returning one
each. Kept apart from api/sabha/schemas.py, which shapes what the REST
API exchanges with a browser; these shapes exist only between this
process and the model.
"""

from typing import Literal

from sqlmodel import SQLModel

VariantAxis = Literal[
    "narrow_scope", "concede_premise", "procedural_reframe", "split_conjunction"
]


class GeneratedVariant(SQLModel):
    """One reformulation of a target statement, along one named axis.

    The axis is one of the four techniques in section 6.3 of the project
    description: narrow what the statement claims, concede one side's
    premise while keeping the other's substance, swap a contested value
    claim for a procedural one, or split a conjunction into its parts.
    """

    text: str
    axis: VariantAxis


class TargetVariants(SQLModel):
    target_statement_id: int
    variants: list[GeneratedVariant]


class VariantBatch(SQLModel):
    target_variants: list[TargetVariants]


class DraftedClause(SQLModel):
    """A clause drafted from one or more statements' supported text.

    statement_ids records provenance: which statements in the pool this
    clause's text was drafted from, so the clause can always be traced
    back to what participants actually voted on.
    """

    statement_ids: list[int]
    text: str


class ClauseDraftBatch(SQLModel):
    drafts: list[DraftedClause]


class RoutingCandidate(SQLModel):
    """One department's routing decision for one clause.

    Multi label by construction: a clause can receive more than one of
    these, one per department whose mandate plausibly covers it, per
    section 6.5.
    """

    clause_id: int
    department: str
    citation: str
    confidence: float
    rationale: str


class RoutingBatch(SQLModel):
    routings: list[RoutingCandidate]


class ReplyJudgement(SQLModel):
    """Whether one reply engaged with the substance of what was filed.

    engagement_score runs 0 to 1: low for boilerplate that does not
    address the clauses submitted, high for a reply that visibly
    responds to their specific content.
    """

    reply_id: int
    engagement_score: float
    rationale: str


class ReplyJudgementBatch(SQLModel):
    judgements: list[ReplyJudgement]
