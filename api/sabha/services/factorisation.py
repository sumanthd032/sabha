"""Bridging factorisation model.

Fits, over observed vote entries only:

    v(i, j)  ~=  mu(j) + b(i) + <f(i), g(j)>

where mu(j) is statement j's bridging score, b(i) is participant i's
general propensity to agree, f(i) is the participant's position in a
low dimensional opinion space, and g(j) is how strongly the statement
loads on that space. This is section 6.1 of the project description,
implemented here by hand with alternating least squares: no matrix
factorisation library is used, which is the only way the model stays
something a person can audit and defend rather than a black box import.

Each alternating step is a small, closed form ridge regression:

  - mu(j) is a ridge-shrunk mean of the residual across everyone who
    voted on statement j: sum(residual) / (n_j + lambda_mu).
  - b(i) is the same shrinkage across every statement participant i voted on.
  - f(i) solves (Gᵀ G + lambda_f I) f = Gᵀ r for the statements i voted
    on, where G stacks their g(j) rows and r is the residual after
    removing mu and b.
  - g(j) is the symmetric update, solving against the f(i) rows of
    everyone who voted on j.

lambda_mu is deliberately the weakest of the four penalties. Shrinking
mu(j) less than f, g, and b biases the fit towards explaining agreement
as broad rather than factional, which is the conservative direction:
the model has to work harder to explain a statement's popularity away
as factional than to simply credit it to the intercept.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy import sparse


@dataclass(frozen=True)
class FactorisationParams:
    num_factors: int = 2
    lambda_factor: float = 0.1
    lambda_bias: float = 0.1
    lambda_intercept: float = 0.01
    iterations: int = 25
    seed: int = 0


@dataclass(frozen=True)
class FactorisationResult:
    participant_ids: list[int]
    statement_ids: list[int]
    mu: np.ndarray
    b: np.ndarray
    f: np.ndarray
    g: np.ndarray
    params: FactorisationParams
    loss_history: list[float] = field(default_factory=list)

    def mu_by_statement(self) -> dict[int, float]:
        return {sid: float(self.mu[j]) for j, sid in enumerate(self.statement_ids)}

    def factor_by_participant(self) -> dict[int, list[float]]:
        return {pid: self.f[i].tolist() for i, pid in enumerate(self.participant_ids)}


def build_vote_matrix(
    participant_ids: list[int],
    statement_ids: list[int],
    votes: list[tuple[int, int, int]],
) -> sparse.csr_matrix:
    """A sparse participant by statement matrix of {-1, +1} votes.

    A pair absent from `votes` is absent from the matrix, never a zero:
    zero is not on the scale of an agree or disagree vote, so treating
    a missing vote as zero would tell the model something no one said.
    """
    p_index = {pid: row for row, pid in enumerate(participant_ids)}
    s_index = {sid: col for col, sid in enumerate(statement_ids)}
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for participant_id, statement_id, value in votes:
        if participant_id not in p_index or statement_id not in s_index:
            continue
        rows.append(p_index[participant_id])
        cols.append(s_index[statement_id])
        data.append(float(value))
    matrix = sparse.coo_matrix(
        (np.array(data), (np.array(rows), np.array(cols))),
        shape=(len(participant_ids), len(statement_ids)),
    )
    return matrix.tocsr()


def _compute_loss(
    vote_matrix: sparse.csr_matrix,
    mu: np.ndarray,
    b: np.ndarray,
    f: np.ndarray,
    g: np.ndarray,
    params: FactorisationParams,
) -> float:
    coo = vote_matrix.tocoo()
    predicted = mu[coo.col] + b[coo.row] + np.einsum("ik,ik->i", f[coo.row], g[coo.col])
    data_loss = float(np.sum((coo.data - predicted) ** 2))
    reg_loss = (
        params.lambda_factor * float(np.sum(f**2))
        + params.lambda_factor * float(np.sum(g**2))
        + params.lambda_bias * float(np.sum(b**2))
        + params.lambda_intercept * float(np.sum(mu**2))
    )
    return data_loss + reg_loss


def fit(
    participant_ids: list[int],
    statement_ids: list[int],
    votes: list[tuple[int, int, int]],
    params: FactorisationParams | None = None,
) -> FactorisationResult:
    """Fit the bridging factorisation model by alternating least squares.

    Deterministic given the same inputs and params: the only randomness
    is the initial f and g draw, seeded from params.seed, and every
    update after that is a fixed sequence of closed form solves. Two
    calls with identical arguments produce identical output, which is
    what lets a model run be reproduced from its snapshot later.
    """
    params = params or FactorisationParams()
    vote_matrix = build_vote_matrix(participant_ids, statement_ids, votes)
    vote_matrix_by_column = vote_matrix.tocsc()
    n_participants, n_statements = vote_matrix.shape
    rng = np.random.default_rng(params.seed)

    mu = np.zeros(n_statements)
    b = np.zeros(n_participants)
    f = rng.normal(0.0, 0.1, size=(n_participants, params.num_factors))
    g = rng.normal(0.0, 0.1, size=(n_statements, params.num_factors))
    identity = np.eye(params.num_factors)

    loss_history: list[float] = []
    for _ in range(params.iterations):
        for j in range(n_statements):
            start, end = vote_matrix_by_column.indptr[j], vote_matrix_by_column.indptr[j + 1]
            rows_seen = vote_matrix_by_column.indices[start:end]
            if len(rows_seen) == 0:
                mu[j] = 0.0
                continue
            values = vote_matrix_by_column.data[start:end]
            residual = values - b[rows_seen] - np.einsum("nk,k->n", f[rows_seen], g[j])
            mu[j] = residual.sum() / (len(rows_seen) + params.lambda_intercept)

        for i in range(n_participants):
            start, end = vote_matrix.indptr[i], vote_matrix.indptr[i + 1]
            cols_seen = vote_matrix.indices[start:end]
            if len(cols_seen) == 0:
                b[i] = 0.0
                continue
            values = vote_matrix.data[start:end]
            residual = values - mu[cols_seen] - np.einsum("nk,k->n", g[cols_seen], f[i])
            b[i] = residual.sum() / (len(cols_seen) + params.lambda_bias)

        for i in range(n_participants):
            start, end = vote_matrix.indptr[i], vote_matrix.indptr[i + 1]
            cols_seen = vote_matrix.indices[start:end]
            if len(cols_seen) == 0:
                continue
            values = vote_matrix.data[start:end]
            residual = values - mu[cols_seen] - b[i]
            g_seen = g[cols_seen]
            f[i] = np.linalg.solve(
                g_seen.T @ g_seen + params.lambda_factor * identity, g_seen.T @ residual
            )

        for j in range(n_statements):
            start, end = vote_matrix_by_column.indptr[j], vote_matrix_by_column.indptr[j + 1]
            rows_seen = vote_matrix_by_column.indices[start:end]
            if len(rows_seen) == 0:
                continue
            values = vote_matrix_by_column.data[start:end]
            residual = values - mu[j] - b[rows_seen]
            f_seen = f[rows_seen]
            g[j] = np.linalg.solve(
                f_seen.T @ f_seen + params.lambda_factor * identity, f_seen.T @ residual
            )

        loss_history.append(_compute_loss(vote_matrix, mu, b, f, g, params))

    return FactorisationResult(
        participant_ids=participant_ids,
        statement_ids=statement_ids,
        mu=mu,
        b=b,
        f=f,
        g=g,
        params=params,
        loss_history=loss_history,
    )


def majority_baseline(
    statement_ids: list[int], votes: list[tuple[int, int, int]]
) -> dict[int, float]:
    """The naive score every consultation tool defaults to: mean vote value.

    Kept here so the bridging ranking always has something to be
    compared against, in code and in tests, rather than only in prose.
    """
    totals: dict[int, float] = dict.fromkeys(statement_ids, 0.0)
    counts: dict[int, int] = dict.fromkeys(statement_ids, 0)
    for _, statement_id, value in votes:
        if statement_id not in totals:
            continue
        totals[statement_id] += value
        counts[statement_id] += 1
    return {sid: (totals[sid] / counts[sid] if counts[sid] else 0.0) for sid in statement_ids}
