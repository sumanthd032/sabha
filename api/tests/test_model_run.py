"""Tests for persisting a factorisation fit as a model_run snapshot."""

from sqlmodel import Session, SQLModel, create_engine

from sabha.seed.loader import load_seed
from sabha.services.factorisation import FactorisationParams
from sabha.services.model_run import fit_and_persist


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_fit_and_persist_writes_a_model_run_snapshot() -> None:
    with _fresh_session() as session:
        load_seed(session, num_participants=120, seed=5)
        params = FactorisationParams(iterations=10)
        model_run = fit_and_persist(session, consultation_id=1, params=params)

        assert model_run.id is not None
        assert model_run.k_clusters >= 2
        assert len(model_run.statement_intercepts) == len(model_run.statement_loadings)
        assert len(model_run.participant_factors) == len(model_run.participant_biases)
        assert len(model_run.cluster_assignments) == len(model_run.participant_factors)


def test_refitting_the_same_snapshot_reproduces_identical_figures() -> None:
    params = FactorisationParams(iterations=10, seed=3)

    with _fresh_session() as session:
        load_seed(session, num_participants=120, seed=6)
        first = fit_and_persist(session, consultation_id=1, params=params)
        first_intercepts = dict(first.statement_intercepts)
        first_factors = dict(first.participant_factors)
        first_biases = dict(first.participant_biases)
        first_k = first.k_clusters

        second = fit_and_persist(session, consultation_id=1, params=params)
        second_intercepts = dict(second.statement_intercepts)
        second_factors = dict(second.participant_factors)
        second_biases = dict(second.participant_biases)
        second_k = second.k_clusters

    assert first_intercepts == second_intercepts
    assert first_factors == second_factors
    assert first_biases == second_biases
    assert first_k == second_k
