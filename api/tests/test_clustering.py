"""Tests for k-means and silhouette-based k selection."""

import numpy as np

from sabha.services.clustering import choose_k, kmeans, silhouette_score


def _three_blobs(seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    centroids = np.array([[0.0, 0.0], [6.0, 0.0], [3.0, 6.0]])
    points = []
    labels = []
    for label, centroid in enumerate(centroids):
        cluster_points = centroid + rng.normal(0.0, 0.5, size=(40, 2))
        points.append(cluster_points)
        labels.append(np.full(40, label))
    return np.concatenate(points), np.concatenate(labels)


def test_kmeans_recovers_well_separated_blobs() -> None:
    points, planted = _three_blobs()
    labels = kmeans(points, k=3, seed=1)

    for cluster in np.unique(labels):
        matching_planted = planted[labels == cluster]
        assert len(np.unique(matching_planted)) == 1


def test_silhouette_score_prefers_the_correct_k() -> None:
    points, _ = _three_blobs()

    scores = {k: silhouette_score(points, kmeans(points, k, seed=1)) for k in (2, 3, 4)}

    assert scores[3] > scores[2]
    assert scores[3] > scores[4]


def test_choose_k_selects_three_for_three_well_separated_blobs() -> None:
    points, _ = _three_blobs()

    best_k, labels = choose_k(points)

    assert best_k == 3
    assert labels.shape == (points.shape[0],)
