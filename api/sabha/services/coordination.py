"""Coordination detection over the participant vote overlap graph.

Section 6.4 of the project description: an organised group voting in
concert produces near identical rows in the vote matrix. This module
builds a similarity graph over participants, restricted to pairs with
enough shared votes to make the comparison meaningful, finds connected
components at a high similarity threshold as candidate tight clusters,
and flags the ones whose internal density and mean agreement both cross
a threshold as coordinated. A flagged cluster is downweighted, never
removed, per the same section: being wrong about a real community
should degrade its influence, not erase it. Every flag carries an
evidence record so the decision is auditable rather than a bare number.

Connected components at a similarity threshold is single link
clustering, not a general community detection algorithm such as
Louvain. It is the right tool here because a genuine brigade shows up
as a near clique of near-identical rows, which single link clustering
finds directly, and doing it with scipy.sparse.csgraph keeps the
dependency list to the sparse module the stack already allows rather
than adding a graph library for one function. A genuine loose community
of people who happen to agree a lot, without voting in lockstep, does
not form a near clique at a high similarity threshold and is left alone.
"""

from dataclasses import dataclass

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components


@dataclass(frozen=True)
class CoordinationParams:
    min_overlap: int = 15
    similarity_threshold: float = 0.85
    min_cluster_size: int = 4
    density_threshold: float = 0.8
    downweight_factor: float = 0.2


@dataclass(frozen=True)
class CoordinationEvidence:
    """The record behind one downweighting decision, kept for the audit log."""

    participant_ids: list[int]
    size: int
    internal_density: float
    mean_similarity: float
    mean_overlap: float


def _pairwise_similarity_and_overlap(
    participant_ids: list[int],
    votes: list[tuple[int, int, int]],
    min_overlap: int,
) -> tuple[sparse.csr_matrix, sparse.csr_matrix]:
    """Cosine similarity and shared vote count for every participant pair
    that voted on at least min_overlap of the same statements.

    Only pairs who share a statement can possibly meet the overlap
    threshold, so candidates are found by grouping voters per statement
    rather than scanning every one of the n choose 2 possible pairs.
    """
    p_index = {pid: row for row, pid in enumerate(participant_ids)}
    n = len(participant_ids)

    votes_by_row: dict[int, dict[int, int]] = {row: {} for row in range(n)}
    rows_by_statement: dict[int, list[int]] = {}
    for participant_id, statement_id, value in votes:
        row = p_index.get(participant_id)
        if row is None:
            continue
        votes_by_row[row][statement_id] = value
        rows_by_statement.setdefault(statement_id, []).append(row)

    candidate_pairs: set[tuple[int, int]] = set()
    for rows_sharing in rows_by_statement.values():
        for a in range(len(rows_sharing)):
            for b in range(a + 1, len(rows_sharing)):
                low, high = sorted((rows_sharing[a], rows_sharing[b]))
                candidate_pairs.add((low, high))

    sim_rows, sim_cols, sim_data = [], [], []
    overlap_rows, overlap_cols, overlap_data = [], [], []
    for row_a, row_b in candidate_pairs:
        votes_a = votes_by_row[row_a]
        votes_b = votes_by_row[row_b]
        shared = votes_a.keys() & votes_b.keys()
        if len(shared) < min_overlap:
            continue
        vec_a = np.array([votes_a[sid] for sid in shared], dtype=np.float64)
        vec_b = np.array([votes_b[sid] for sid in shared], dtype=np.float64)
        similarity = float(np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b)))
        for r, c in ((row_a, row_b), (row_b, row_a)):
            sim_rows.append(r)
            sim_cols.append(c)
            sim_data.append(similarity)
            overlap_rows.append(r)
            overlap_cols.append(c)
            overlap_data.append(float(len(shared)))

    similarity_graph = sparse.csr_matrix((sim_data, (sim_rows, sim_cols)), shape=(n, n))
    overlap_graph = sparse.csr_matrix((overlap_data, (overlap_rows, overlap_cols)), shape=(n, n))
    return similarity_graph, overlap_graph


def detect_coordination(
    participant_ids: list[int],
    votes: list[tuple[int, int, int]],
    params: CoordinationParams | None = None,
) -> tuple[dict[int, float], list[CoordinationEvidence]]:
    """Return a per-participant weight multiplier and the evidence behind
    every downweighting decision.

    A participant outside every flagged cluster keeps a weight of 1.0.
    The weights are meant to be passed straight to
    factorisation.fit(..., participant_weights=...).
    """
    params = params or CoordinationParams()
    similarity_graph, overlap_graph = _pairwise_similarity_and_overlap(
        participant_ids, votes, params.min_overlap
    )

    thresholded = similarity_graph.copy()
    thresholded.data = np.where(
        thresholded.data >= params.similarity_threshold, thresholded.data, 0.0
    )
    thresholded.eliminate_zeros()

    n_components, labels = connected_components(thresholded, directed=False)

    weights = dict.fromkeys(participant_ids, 1.0)
    evidence: list[CoordinationEvidence] = []

    for component in range(n_components):
        member_rows = np.where(labels == component)[0]
        size = len(member_rows)
        if size < params.min_cluster_size:
            continue

        submatrix = thresholded[member_rows][:, member_rows]
        possible_edges = size * (size - 1) / 2
        actual_edges = submatrix.nnz / 2
        density = actual_edges / possible_edges if possible_edges > 0 else 0.0
        if density < params.density_threshold:
            continue

        mean_similarity = float(submatrix.data.mean()) if submatrix.nnz > 0 else 0.0
        overlap_submatrix = overlap_graph[member_rows][:, member_rows]
        mean_overlap = float(overlap_submatrix.data.mean()) if overlap_submatrix.nnz > 0 else 0.0

        member_ids = [participant_ids[row] for row in member_rows]
        for participant_id in member_ids:
            weights[participant_id] = params.downweight_factor
        evidence.append(
            CoordinationEvidence(
                participant_ids=member_ids,
                size=size,
                internal_density=density,
                mean_similarity=mean_similarity,
                mean_overlap=mean_overlap,
            )
        )

    return weights, evidence
