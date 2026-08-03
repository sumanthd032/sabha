"""Tests for the synthetic seed corpus and vote generator."""

import numpy as np
from sqlmodel import Session, SQLModel, create_engine, select

from sabha.models import Consultation, Participant, Statement
from sabha.seed.generator import FACTION_LEANINGS, generate_corpus
from sabha.seed.loader import load_seed
from sabha.seed.statements import STATEMENTS


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_seed_loads_expected_row_counts() -> None:
    with _fresh_session() as session:
        counts = load_seed(session, num_participants=150, seed=1)

    assert counts["statements"] == len(STATEMENTS)
    assert counts["participants"] == 150
    assert 150 * 8 <= counts["votes"] <= 150 * 30


def test_seed_data_is_labelled_synthetic_throughout() -> None:
    with _fresh_session() as session:
        load_seed(session, num_participants=20, seed=2)

        consultation = session.exec(select(Consultation)).one()
        assert consultation.is_synthetic is True

        statements = session.exec(select(Statement)).all()
        assert statements and all(s.is_synthetic for s in statements)

        participants = session.exec(select(Participant)).all()
        assert participants and all(p.is_synthetic for p in participants)
        assert all(p.planted_factor is not None for p in participants)
        assert all(p.planted_cluster is not None for p in participants)


def test_vote_matrix_is_sparse() -> None:
    with _fresh_session() as session:
        counts = load_seed(session, num_participants=200, seed=3)

    total_cells = counts["statements"] * counts["participants"]
    density = counts["votes"] / total_cells
    assert density < 0.4


def test_planted_structure_is_recoverable() -> None:
    """The generator's own output already shows the effect the bridging
    model in step 4 is meant to detect: factional statements split along
    planted faction lines, bridging statements do not.
    """
    corpus = generate_corpus(num_participants=600, seed=4)

    votes_by_pair: dict[tuple[int, int], list[int]] = {}
    for p_index, s_index, value in corpus.votes:
        votes_by_pair.setdefault((p_index, s_index), []).append(value)

    def agreement_rate(statement_indices: list[int], faction: int | None) -> float:
        values: list[int] = []
        for p_index, participant in enumerate(corpus.participants):
            if faction is not None and participant.faction != faction:
                continue
            for s_index in statement_indices:
                for value in votes_by_pair.get((p_index, s_index), []):
                    values.append(1 if value == 1 else 0)
        return float(np.mean(values)) if values else float("nan")

    bridging_indices = [i for i, s in enumerate(STATEMENTS) if s.leaning == "bridging"]
    bridging_rates_by_faction = [
        agreement_rate(bridging_indices, faction) for faction in range(len(FACTION_LEANINGS))
    ]
    assert min(bridging_rates_by_faction) > 0.6
    assert max(bridging_rates_by_faction) - min(bridging_rates_by_faction) < 0.15

    for faction_index, leaning in enumerate(FACTION_LEANINGS):
        aligned_indices = [i for i, s in enumerate(STATEMENTS) if s.leaning == leaning]
        in_faction_rate = agreement_rate(aligned_indices, faction_index)
        out_of_faction_rates = [
            agreement_rate(aligned_indices, other)
            for other in range(len(FACTION_LEANINGS))
            if other != faction_index
        ]
        assert in_faction_rate - max(out_of_faction_rates) > 0.2
