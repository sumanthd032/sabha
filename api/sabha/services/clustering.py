"""K-means over fitted participant factors, with k chosen by silhouette score.

Neither scikit-learn nor any other clustering library is on the approved
dependency list in section 4 of the build instructions, so both Lloyd's
algorithm and the silhouette score are written here directly on top of
numpy. Named factions are a display convenience only: the bridging
ranking in factorisation.py does not depend on getting k right, per
section 6.1 of the project description.
"""

import numpy as np

DEFAULT_K_RANGE = range(2, 7)


def _pairwise_distances(points: np.ndarray) -> np.ndarray:
    sq_norms = np.sum(points**2, axis=1)
    sq_dists = sq_norms[:, None] + sq_norms[None, :] - 2 * points @ points.T
    return np.asarray(np.sqrt(np.maximum(sq_dists, 0.0)), dtype=np.float64)


def kmeans(points: np.ndarray, k: int, iterations: int = 100, seed: int = 0) -> np.ndarray:
    """Lloyd's algorithm. Returns one cluster label per point."""
    n = points.shape[0]
    rng = np.random.default_rng(seed)
    centroids = points[rng.choice(n, size=k, replace=False)].copy()
    labels = np.full(n, -1, dtype=int)

    for _ in range(iterations):
        dists = np.linalg.norm(points[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for cluster in range(k):
            members = points[labels == cluster]
            if len(members) > 0:
                centroids[cluster] = members.mean(axis=0)
    return labels


def silhouette_score(points: np.ndarray, labels: np.ndarray) -> float:
    """Mean silhouette coefficient across all points, in [-1, 1]."""
    n = points.shape[0]
    unique_labels = np.unique(labels)
    if n < 3 or len(unique_labels) < 2:
        return -1.0

    dists = _pairwise_distances(points)
    scores = np.zeros(n)
    for idx in range(n):
        own_label = labels[idx]
        own_mask = labels == own_label
        own_mask[idx] = False
        if not own_mask.any():
            continue
        a = dists[idx, own_mask].mean()
        b = min(
            dists[idx, labels == other].mean() for other in unique_labels if other != own_label
        )
        scores[idx] = (b - a) / max(a, b) if max(a, b) > 0 else 0.0
    return float(scores.mean())


def choose_k(
    points: np.ndarray, k_range: range = DEFAULT_K_RANGE, seed: int = 0
) -> tuple[int, np.ndarray]:
    """Pick k over a small range by silhouette score, returning the winning labels."""
    best_k = k_range.start
    best_score = -1.0
    best_labels = np.zeros(points.shape[0], dtype=int)
    for k in k_range:
        if k >= points.shape[0]:
            continue
        labels = kmeans(points, k, seed=seed)
        score = silhouette_score(points, labels)
        if score > best_score:
            best_score = score
            best_k = k
            best_labels = labels
    return best_k, best_labels
