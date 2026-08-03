"""Synthetic participants and votes with a planted latent structure.

Generates data consistent with the bridging factorisation model in
section 6.1 of the project specification:

    v(i, j) ~= mu(j) + b(i) + <f(i), g(j)>

so that fitting the real model against this data in step 4 has a known
answer to recover, rather than only synthetic-looking numbers with
nothing to check them against.

Three synthetic factions are planted in a two dimensional opinion space,
one centred on each of the worker, platform, and regulator leanings used
to tag statements in statements.py. A statement tagged "bridging" gets a
loading vector near zero, so no faction's position explains its
agreement and the intercept absorbs it instead: exactly the effect the
bridging score is meant to isolate. A statement tagged with a leaning
gets a loading vector pointing at that faction's centroid, so
participants near that centroid agree with it far more than participants
near the other two.

Voting is sparse by construction, not by omission: each synthetic
participant is given a random subset of statements to vote on, and every
statement outside that subset is simply absent from the generated vote
list, the same "did not see" semantics real votes carry.
"""

from dataclasses import dataclass

import numpy as np

from sabha.seed.statements import STATEMENTS, Leaning

NUM_LATENT_DIMS = 2
NUM_FACTIONS = 3
FACTION_LEANINGS: tuple[Leaning, ...] = ("worker", "platform", "regulator")
FACTION_RADIUS = 1.5
FACTION_SPREAD = 0.4
LOADING_NOISE_SPREAD = 0.15
LEANING_LOADING_STRENGTH = (0.8, 1.4)
BRIDGING_INTERCEPT_MEAN = 1.1
LEANING_INTERCEPT_MEAN = 0.0
INTERCEPT_SPREAD = 0.3
BIAS_SPREAD = 0.3
VOTE_NOISE_SPREAD = 0.3
MIN_VOTES_PER_PARTICIPANT = 8
MAX_VOTES_PER_PARTICIPANT = 30


def _faction_centroids() -> np.ndarray:
    """Three points spread evenly around a circle, one per synthetic faction."""
    angles = np.linspace(0, 2 * np.pi, NUM_FACTIONS, endpoint=False) + np.pi / 2
    return FACTION_RADIUS * np.stack([np.cos(angles), np.sin(angles)], axis=1)


@dataclass(frozen=True)
class SyntheticStatement:
    intercept: float
    loading: np.ndarray


@dataclass(frozen=True)
class SyntheticParticipant:
    faction: int
    factor: np.ndarray
    bias: float


@dataclass(frozen=True)
class GeneratedCorpus:
    statements: list[SyntheticStatement]
    participants: list[SyntheticParticipant]
    votes: list[tuple[int, int, int]]
    """Each vote is (participant_index, statement_index, value)."""


def _generate_statements(rng: np.random.Generator) -> list[SyntheticStatement]:
    centroids = _faction_centroids()
    out = []
    for statement in STATEMENTS:
        if statement.leaning == "bridging":
            intercept = rng.normal(BRIDGING_INTERCEPT_MEAN, INTERCEPT_SPREAD)
            loading = rng.normal(0.0, LOADING_NOISE_SPREAD, size=NUM_LATENT_DIMS)
        else:
            faction_index = FACTION_LEANINGS.index(statement.leaning)
            direction = centroids[faction_index]
            direction = direction / np.linalg.norm(direction)
            strength = rng.uniform(*LEANING_LOADING_STRENGTH)
            noise = rng.normal(0.0, LOADING_NOISE_SPREAD, size=NUM_LATENT_DIMS)
            loading = direction * strength + noise
            intercept = rng.normal(LEANING_INTERCEPT_MEAN, INTERCEPT_SPREAD)
        out.append(SyntheticStatement(intercept=float(intercept), loading=loading))
    return out


def _generate_participants(
    count: int, rng: np.random.Generator, faction_weights: list[float] | None = None
) -> list[SyntheticParticipant]:
    """faction_weights lets a caller plant an unequal split, such as one
    large majority bloc and two smaller ones, the scenario majority
    counting gets wrong and the bridging score is meant to get right.
    Defaults to an even split across the three synthetic factions.
    """
    centroids = _faction_centroids()
    weights = np.array(faction_weights) if faction_weights else None
    out = []
    for _ in range(count):
        if weights is not None:
            faction = int(rng.choice(NUM_FACTIONS, p=weights))
        else:
            faction = int(rng.integers(0, NUM_FACTIONS))
        factor = centroids[faction] + rng.normal(0.0, FACTION_SPREAD, size=NUM_LATENT_DIMS)
        bias = float(rng.normal(0.0, BIAS_SPREAD))
        out.append(SyntheticParticipant(faction=faction, factor=factor, bias=bias))
    return out


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


def generate_corpus(
    num_participants: int = 300,
    seed: int = 0,
    faction_weights: list[float] | None = None,
) -> GeneratedCorpus:
    """Plant a latent structure and sample sparse votes consistent with it.

    seed fixes the numpy generator so a development rerun produces the
    same synthetic population, which matters for reproducing whatever a
    test or a demo run saw the first time. faction_weights defaults to
    an even three way split; pass an unequal one to plant a majority
    bloc for testing that the bridging score does not simply reward it.
    """
    rng = np.random.default_rng(seed)
    statements = _generate_statements(rng)
    participants = _generate_participants(num_participants, rng, faction_weights)

    votes: list[tuple[int, int, int]] = []
    statement_indices = np.arange(len(statements))
    for p_index, participant in enumerate(participants):
        num_votes = int(rng.integers(MIN_VOTES_PER_PARTICIPANT, MAX_VOTES_PER_PARTICIPANT + 1))
        num_votes = min(num_votes, len(statements))
        seen = rng.choice(statement_indices, size=num_votes, replace=False)
        for s_index in seen:
            statement = statements[int(s_index)]
            score = (
                statement.intercept
                + participant.bias
                + float(np.dot(participant.factor, statement.loading))
                + rng.normal(0.0, VOTE_NOISE_SPREAD)
            )
            value = 1 if rng.random() < _sigmoid(score) else -1
            votes.append((p_index, int(s_index), value))

    return GeneratedCorpus(statements=statements, participants=participants, votes=votes)
