"""Tests for adaptive statement selection against random ordering."""

import numpy as np

from sabha.seed.generator import generate_corpus
from sabha.seed.statements import STATEMENTS
from sabha.services.factorisation import FactorisationParams, FactorisationResult, fit
from sabha.services.selection import (
    SelectionParams,
    participant_posterior_width,
    select_next_statement,
)

TARGET_WIDTH = 1.0


def _fitted_result() -> FactorisationResult:
    corpus = generate_corpus(num_participants=400, seed=1)
    participant_ids = list(range(len(corpus.participants)))
    statement_ids = list(range(len(STATEMENTS)))
    return fit(participant_ids, statement_ids, corpus.votes, FactorisationParams(iterations=30))


def _steps_to_target(
    statement_ids: list[int], ordered: list[int], result: FactorisationResult
) -> int:
    for step in range(1, len(ordered) + 1):
        seen = ordered[:step]
        loadings = result.g[[statement_ids.index(sid) for sid in seen]]
        width = participant_posterior_width(
            loadings, result.params.lambda_factor, result.params.num_factors
        )
        if width <= TARGET_WIDTH:
            return step
    raise AssertionError("target width never reached")


def test_adaptive_selection_reaches_target_width_in_fewer_votes_than_random() -> None:
    result = _fitted_result()
    statement_ids = result.statement_ids
    params = SelectionParams(locate_posterior_width=2.0, exposure_cap=10_000, reserve_fraction=0.0)
    rng = np.random.default_rng(0)

    adaptive_order: list[int] = []
    voted: set[int] = set()
    counts: dict[int, int] = {}
    while True:
        sid = select_next_statement(result, statement_ids, voted, counts, params, rng)
        assert sid is not None
        voted.add(sid)
        counts[sid] = counts.get(sid, 0) + 1
        adaptive_order.append(sid)
        loadings = result.g[[statement_ids.index(s) for s in voted]]
        width = participant_posterior_width(
            loadings, result.params.lambda_factor, result.params.num_factors
        )
        if width <= TARGET_WIDTH:
            break
    adaptive_steps = len(adaptive_order)

    random_steps = []
    for seed in range(20):
        shuffle_rng = np.random.default_rng(seed)
        order = list(statement_ids)
        shuffle_rng.shuffle(order)
        random_steps.append(_steps_to_target(statement_ids, order, result))

    assert adaptive_steps < np.median(random_steps) / 2


def test_select_next_statement_never_repeats_or_exceeds_the_exposure_cap() -> None:
    result = _fitted_result()
    statement_ids = result.statement_ids
    params = SelectionParams(locate_posterior_width=2.0, exposure_cap=2, reserve_fraction=0.1)
    rng = np.random.default_rng(3)

    voted: set[int] = set()
    counts: dict[int, int] = dict.fromkeys(statement_ids, 0)
    for _ in range(len(statement_ids)):
        sid = select_next_statement(result, statement_ids, voted, counts, params, rng)
        if sid is None:
            break
        assert sid not in voted
        voted.add(sid)
        counts[sid] += 1

    assert all(count <= params.exposure_cap for count in counts.values())


def test_select_next_statement_returns_none_when_nothing_is_eligible() -> None:
    result = _fitted_result()
    statement_ids = result.statement_ids
    params = SelectionParams(exposure_cap=1, reserve_fraction=0.0)
    rng = np.random.default_rng(4)

    voted = set(statement_ids)
    counts = dict.fromkeys(statement_ids, 1)

    assert select_next_statement(result, statement_ids, voted, counts, params, rng) is None
