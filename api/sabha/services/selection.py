"""Adaptive statement selection: two-phase experimental design over the
bridging factorisation fit.

Section 6.2 of the project description casts voting order as sequential
experimental design rather than a fixed order, since a participant on a
slow connection gives eight votes, not sixty, and each one has to earn
its place.

Locate phase. A participant's opinion position f(i) is fit from the
statements they have voted on by a ridge regression against the fitted
loadings g(j) of those statements, per factorisation.py. Under a
Gaussian approximation, the posterior covariance of that regression is

    Cov(f(i)) = (G_i^T G_i + lambda_f I)^-1

where G_i stacks g(j) for every statement i has voted on. Its trace is
the posterior width used here. With no votes yet, G_i is empty and the
width is num_factors / lambda_f, the widest it gets. Serving statements
with a large loading norm |g(j)| shrinks this the fastest, because a
statement that discriminates strongly along the opinion axes moves the
estimate the most per vote; this is the rule of thumb version of the
full D-optimal design the project description names, cheap enough to
evaluate over a candidate pool on every vote.

Refine phase. Once that width falls under a threshold, the objective
switches to the statement's own posterior. mu(j)'s posterior variance
under the same ridge interpretation is 1 / (n_j + lambda_mu), so serving
the statement with the fewest votes so far shrinks that statement's own
uncertainty the fastest, and a vote from an already well placed
participant is worth the most towards resolving it.

Exposure is capped per statement, and a small reserve of slots is
chosen uniformly at random regardless of phase, so the policy cannot
become self-confirming by only ever asking about what it already
suspects.
"""

from dataclasses import dataclass

import numpy as np

from sabha.services.factorisation import FactorisationResult


@dataclass(frozen=True)
class SelectionParams:
    locate_posterior_width: float = 2.0
    exposure_cap: int = 300
    reserve_fraction: float = 0.1


def participant_posterior_width(
    voted_loadings: np.ndarray, lambda_factor: float, num_factors: int
) -> float:
    """trace(Cov(f(i))) given the fitted g(j) of every statement voted on so far."""
    if voted_loadings.shape[0] == 0:
        return float(num_factors / lambda_factor)
    identity = np.eye(num_factors)
    precision = voted_loadings.T @ voted_loadings + lambda_factor * identity
    covariance = np.linalg.inv(precision)
    return float(np.trace(covariance))


def statement_posterior_width(vote_count: int, lambda_intercept: float) -> float:
    """1 / (n_j + lambda_mu), the ridge posterior variance behind mu(j)."""
    return 1.0 / (vote_count + lambda_intercept)


def select_next_statement(
    result: FactorisationResult,
    candidate_statement_ids: list[int],
    voted_statement_ids: set[int],
    statement_vote_counts: dict[int, int],
    params: SelectionParams,
    rng: np.random.Generator,
) -> int | None:
    """Choose the next statement to serve one participant.

    candidate_statement_ids must already be a subset of result.statement_ids:
    a statement only becomes selectable once it has a fitted g(j) and mu(j)
    from the most recent model run, so a freshly injected statement joins
    the candidate pool at the next refit, not before.
    """
    statement_index = {sid: j for j, sid in enumerate(result.statement_ids)}
    eligible = [
        sid
        for sid in candidate_statement_ids
        if sid not in voted_statement_ids
        and statement_vote_counts.get(sid, 0) < params.exposure_cap
    ]
    if not eligible:
        return None

    if rng.random() < params.reserve_fraction:
        return int(rng.choice(eligible))

    voted_indices = [
        statement_index[sid] for sid in voted_statement_ids if sid in statement_index
    ]
    voted_loadings = result.g[voted_indices] if voted_indices else np.empty((0, result.g.shape[1]))
    width = participant_posterior_width(
        voted_loadings, result.params.lambda_factor, result.params.num_factors
    )

    if width > params.locate_posterior_width:
        scores = {sid: float(np.linalg.norm(result.g[statement_index[sid]])) for sid in eligible}
    else:
        scores = {
            sid: statement_posterior_width(
                statement_vote_counts.get(sid, 0), result.params.lambda_intercept
            )
            for sid in eligible
        }

    return max(scores, key=lambda sid: scores[sid])
