"""Jurisdiction routing over the Allocation of Business Rules.

Section 6.5 of the project description: routing is a retrieval problem
with a checkable answer, not a guess. For each clause, the candidate
departments are retrieved by embedding similarity against the indexed
AllocationRule mandates, then a single batched call asks the model for
a routing decision citing one of exactly those candidates. A citation
the model returns that does not match an offered candidate is dropped
rather than trusted: the point of grounding this in retrieval is that
every citation in the database is checkable against a real candidate,
never invented.

A clause can receive more than one RoutingDecision, one per department
whose mandate plausibly covers it, since real subject matter such as
platform work genuinely spans more than one ministry. There is no
sentinel row for "no route found": a clause with too low a confidence
on every candidate, or with no candidate at all, simply has no
confident RoutingDecision, and clauses_awaiting_human_review reads that
absence back out as the human queue rather than storing it twice.
"""

from dataclasses import dataclass

import numpy as np
from sqlmodel import Session, col, select

from sabha.llm.client import GenaiClient, call_embedding, call_structured, load_prompt
from sabha.llm.schemas import RoutingBatch
from sabha.models import AllocationRule, Clause, RoutingDecision
from sabha.services.quota import QuotaGuard


@dataclass(frozen=True)
class RoutingParams:
    top_k_candidates: int = 3
    confidence_threshold: float = 0.6


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def retrieve_candidates(
    clause_embedding: list[float], rules: list[AllocationRule], params: RoutingParams
) -> list[AllocationRule]:
    """The top_k_candidates rules whose mandate is most similar to the
    clause by cosine similarity of the embeddings, best first.
    """
    if not rules:
        return []
    clause_vector = np.array(clause_embedding)
    scored = [(_cosine_similarity(clause_vector, np.array(rule.embedding)), rule) for rule in rules]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [rule for _, rule in scored[: params.top_k_candidates]]


def _format_clauses_block(
    clauses: list[Clause], candidates_by_clause: dict[int, list[AllocationRule]]
) -> str:
    blocks = []
    for clause in clauses:
        assert clause.id is not None
        candidate_lines = "\n".join(
            f'- department: "{rule.department}", citation: "{rule.citation}", '
            f'mandate: "{rule.mandate_text}"'
            for rule in candidates_by_clause[clause.id]
        )
        blocks.append(
            f"Clause id {clause.id}:\n\"{clause.text}\"\nCandidate departments:\n{candidate_lines}"
        )
    return "\n\n".join(blocks)


def _persist_routing_batch(
    session: Session,
    batch: RoutingBatch,
    candidates_by_clause: dict[int, list[AllocationRule]],
    params: RoutingParams,
) -> list[RoutingDecision]:
    decisions: list[RoutingDecision] = []
    for entry in batch.routings:
        candidates = candidates_by_clause.get(entry.clause_id, [])
        matching_rule = next(
            (
                rule
                for rule in candidates
                if rule.citation == entry.citation and rule.department == entry.department
            ),
            None,
        )
        if matching_rule is None or matching_rule.id is None:
            continue
        decision = RoutingDecision(
            clause_id=entry.clause_id,
            allocation_rule_id=matching_rule.id,
            department=entry.department,
            citation=entry.citation,
            confidence=entry.confidence,
            rationale=entry.rationale,
            needs_human_review=entry.confidence < params.confidence_threshold,
        )
        session.add(decision)
        decisions.append(decision)
    return decisions


def route_clauses(
    session: Session,
    quota: QuotaGuard,
    clauses: list[Clause],
    params: RoutingParams | None = None,
    genai_client: GenaiClient | None = None,
) -> list[RoutingDecision]:
    """Route one or more clauses in a single batched call.

    Makes no call at all, spending no quota, when there is no indexed
    rule to retrieve against or no clause retrieves a candidate.
    """
    params = params or RoutingParams()
    if not clauses:
        return []

    rules = list(session.exec(select(AllocationRule)).all())
    if not rules:
        return []

    candidates_by_clause: dict[int, list[AllocationRule]] = {}
    for clause in clauses:
        assert clause.id is not None
        clause_embedding = call_embedding(session, quota, clause.text, genai_client=genai_client)
        candidates = retrieve_candidates(clause_embedding, rules, params)
        if candidates:
            candidates_by_clause[clause.id] = candidates

    if not candidates_by_clause:
        return []

    routable_clauses = [c for c in clauses if c.id in candidates_by_clause]
    clauses_block = _format_clauses_block(routable_clauses, candidates_by_clause)
    prompt = load_prompt("route_clause", clauses=clauses_block)
    batch = call_structured(
        session, quota, prompt, RoutingBatch, "RoutingBatch", genai_client=genai_client
    )

    decisions = _persist_routing_batch(session, batch, candidates_by_clause, params)
    session.commit()
    for decision in decisions:
        session.refresh(decision)
    return decisions


def clauses_awaiting_human_review(session: Session, clause_ids: list[int]) -> list[int]:
    """Clause ids from the given set with no confident route.

    A clause reaches the human queue either because no RoutingDecision
    was ever recorded for it, or because every decision recorded for it
    was flagged needs_human_review: section 6.5's rule that a low
    confidence route is queued for a human rather than filed on a
    guess, even when that means every candidate came back uncertain.
    """
    if not clause_ids:
        return []
    decisions = session.exec(
        select(RoutingDecision).where(col(RoutingDecision.clause_id).in_(clause_ids))
    ).all()
    confidently_routed = {d.clause_id for d in decisions if not d.needs_human_review}
    return [clause_id for clause_id in clause_ids if clause_id not in confidently_routed]
