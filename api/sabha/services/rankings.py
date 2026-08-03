"""Bridging and majority rankings for display, from a fitted model run.

Kept as one function so the REST endpoint and the WebSocket broadcast in
services/live.py build the exact same shape from the exact same inputs,
rather than two copies that could quietly drift apart.
"""

from dataclasses import dataclass

from sabha.models import Statement
from sabha.services.factorisation import FactorisationResult, majority_baseline


@dataclass(frozen=True)
class RankedStatement:
    statement_id: int
    code: str
    text: str
    score: float
    rank: int


def build_rankings(
    result: FactorisationResult,
    votes: list[tuple[int, int, int]],
    statements: dict[int, Statement],
) -> tuple[list[RankedStatement], list[RankedStatement]]:
    """Returns (bridging, majority) rankings, each sorted best first.

    A statement absent from `statements`, such as one removed since the
    run was fitted, is silently dropped rather than raising, since a
    ranking is a display list, not a referential integrity check.
    """

    def rank(scores: dict[int, float]) -> list[RankedStatement]:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [
            RankedStatement(
                statement_id=sid,
                code=statements[sid].code,
                text=statements[sid].text,
                score=score,
                rank=position,
            )
            for position, (sid, score) in enumerate(ordered, start=1)
            if sid in statements
        ]

    baseline = majority_baseline(result.statement_ids, votes)
    return rank(result.mu_by_statement()), rank(baseline)
