"""Tests for the bridging factorisation model against planted synthetic data."""

import numpy as np

from sabha.seed.generator import FACTION_LEANINGS, GeneratedCorpus, generate_corpus
from sabha.seed.statements import STATEMENTS
from sabha.services.clustering import choose_k
from sabha.services.factorisation import (
    FactorisationParams,
    FactorisationResult,
    fit,
    majority_baseline,
)

BRIDGING_INDICES = [i for i, s in enumerate(STATEMENTS) if s.leaning == "bridging"]
FACTIONAL_INDICES = [i for i, s in enumerate(STATEMENTS) if s.leaning != "bridging"]


def _fit_corpus(
    seed: int,
    num_participants: int = 400,
    faction_weights: list[float] | None = None,
) -> tuple[GeneratedCorpus, FactorisationResult]:
    corpus = generate_corpus(
        num_participants=num_participants, seed=seed, faction_weights=faction_weights
    )
    participant_ids = list(range(len(corpus.participants)))
    statement_ids = list(range(len(STATEMENTS)))
    result = fit(participant_ids, statement_ids, corpus.votes, FactorisationParams(iterations=30))
    return corpus, result


def _cluster_purity(labels: np.ndarray, planted: np.ndarray) -> float:
    """Fraction of points whose cluster's majority planted faction matches their own."""
    correct = 0
    for cluster in np.unique(labels):
        mask = labels == cluster
        counts = np.bincount(planted[mask], minlength=len(FACTION_LEANINGS))
        correct += int(counts.max())
    return correct / len(labels)


def test_bridging_statements_rank_above_factional_with_a_clear_margin() -> None:
    _, result = _fit_corpus(seed=10)

    bridging_mu = float(np.mean(result.mu[BRIDGING_INDICES]))
    factional_mu = float(np.mean(result.mu[FACTIONAL_INDICES]))

    assert bridging_mu - factional_mu > 0.3


def test_bridging_ranking_beats_majority_baseline_under_a_majority_bloc() -> None:
    """An 80 per cent bloc pushes its own aligned statements up under a plain
    average, since four in five voters are the same people every time. The
    bridging score must resist that pull, which is the whole point of
    factoring viewpoint out of the ranking rather than trusting raw counts.
    """
    corpus, result = _fit_corpus(seed=21, num_participants=600, faction_weights=[0.8, 0.1, 0.1])
    statement_ids = list(range(len(STATEMENTS)))
    baseline = majority_baseline(statement_ids, corpus.votes)
    mu_scores = result.mu_by_statement()

    bridging_set = set(BRIDGING_INDICES)
    k = len(bridging_set)

    def precision_at_k(scores: dict[int, float]) -> float:
        top_k = sorted(scores, key=lambda sid: scores[sid], reverse=True)[:k]
        return len([sid for sid in top_k if sid in bridging_set]) / k

    baseline_precision = precision_at_k(baseline)
    mu_precision = precision_at_k(mu_scores)

    assert mu_precision - baseline_precision > 0.1


def test_clustering_recovers_the_planted_factions() -> None:
    corpus, result = _fit_corpus(seed=12, num_participants=300)
    planted = np.array([p.faction for p in corpus.participants])

    k_clusters, labels = choose_k(result.f)

    assert k_clusters == len(FACTION_LEANINGS)
    assert _cluster_purity(labels, planted) > 0.75


def test_participant_weights_reduce_a_downweighted_blocs_pull_on_mu() -> None:
    """coordination.py hands a downweighted block's ids to fit() as a
    weight below 1.0. Two genuine dissenters against eight full-weight
    agreers would lose a plain vote; once the eight are downweighted the
    intercept should swing back towards the two, matching section 6.4's
    instruction to degrade a coordinated block's influence, not erase it.
    """
    genuine_ids = [0, 1]
    coordinated_ids = list(range(2, 10))
    participant_ids = genuine_ids + coordinated_ids
    statement_ids = [0]
    votes = [(pid, 0, -1) for pid in genuine_ids] + [(pid, 0, 1) for pid in coordinated_ids]

    params = FactorisationParams(iterations=10)
    full_weight = fit(participant_ids, statement_ids, votes, params)
    downweighted = fit(
        participant_ids,
        statement_ids,
        votes,
        params,
        participant_weights=dict.fromkeys(coordinated_ids, 0.1),
    )

    assert full_weight.mu[0] > 0
    assert downweighted.mu[0] < full_weight.mu[0]


def test_refitting_the_same_inputs_reproduces_identical_figures() -> None:
    corpus = generate_corpus(num_participants=150, seed=13)
    participant_ids = list(range(len(corpus.participants)))
    statement_ids = list(range(len(STATEMENTS)))
    params = FactorisationParams(iterations=15, seed=7)

    first = fit(participant_ids, statement_ids, corpus.votes, params)
    second = fit(participant_ids, statement_ids, corpus.votes, params)

    assert np.array_equal(first.mu, second.mu)
    assert np.array_equal(first.b, second.b)
    assert np.array_equal(first.f, second.f)
    assert np.array_equal(first.g, second.g)
