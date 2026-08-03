"""Tests for coordination detection over the vote overlap graph."""

import numpy as np

from sabha.services.coordination import CoordinationParams, detect_coordination

NUM_STATEMENTS = 30


def _genuine_community_votes(
    rng: np.random.Generator, participant_ids: list[int]
) -> list[tuple[int, int, int]]:
    """A real shared lean, not lockstep: each vote flips independently
    about 15 per cent of the time, so no two members ever agree perfectly.
    """
    votes = []
    for pid in participant_ids:
        for sid in range(NUM_STATEMENTS):
            value = 1 if rng.random() < 0.85 else -1
            votes.append((pid, sid, value))
    return votes


def _brigade_votes(
    participant_ids: list[int], targeted_statements: list[int]
) -> list[tuple[int, int, int]]:
    """A coordinated block: every member casts the identical vote on the
    same targeted statements, which is the near identical row signature
    section 6.4 of the project description names.
    """
    pattern = {sid: (1 if sid % 2 == 0 else -1) for sid in targeted_statements}
    return [(pid, sid, value) for pid in participant_ids for sid, value in pattern.items()]


def test_a_synthetic_brigade_is_detected_and_downweighted() -> None:
    rng = np.random.default_rng(7)
    genuine_ids = list(range(20))
    brigade_ids = list(range(1000, 1008))
    targeted_statements = list(range(20))

    votes = _genuine_community_votes(rng, genuine_ids)
    votes += _brigade_votes(brigade_ids, targeted_statements)

    weights, evidence = detect_coordination(genuine_ids + brigade_ids, votes)

    assert len(evidence) == 1
    flagged = evidence[0]
    assert set(flagged.participant_ids) == set(brigade_ids)
    assert flagged.internal_density == 1.0
    assert flagged.mean_similarity > 0.99
    assert all(weights[pid] < 1.0 for pid in brigade_ids)


def test_a_genuine_loose_community_is_not_flagged() -> None:
    rng = np.random.default_rng(7)
    genuine_ids = list(range(20))
    votes = _genuine_community_votes(rng, genuine_ids)

    weights, evidence = detect_coordination(genuine_ids, votes)

    assert evidence == []
    assert all(weight == 1.0 for weight in weights.values())


def test_a_small_brigade_below_the_minimum_cluster_size_is_not_flagged() -> None:
    targeted_statements = list(range(20))
    brigade_ids = [2000, 2001]
    votes = _brigade_votes(brigade_ids, targeted_statements)

    params = CoordinationParams(min_cluster_size=4)
    weights, evidence = detect_coordination(brigade_ids, votes, params)

    assert evidence == []
    assert all(weight == 1.0 for weight in weights.values())
