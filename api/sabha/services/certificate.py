"""The consensus certificate's figures: for one statement, the support
found inside every faction the model run detected.

Section 5.6 of the build instructions: a mono table of support figures
inside every detected faction, alongside the participant count and the
model run identifier. The clause text itself is the certified
statement's own text until the generation loop in a later step can
draft multi-statement clauses; the certificate component does not care
which, since its job is to display whatever text it is given next to
the figures computed here.
"""

from dataclasses import dataclass

from sabha.models import ModelRun


@dataclass(frozen=True)
class ClusterSupport:
    cluster: int
    participant_count: int
    agree_count: int
    agree_fraction: float


@dataclass(frozen=True)
class CertificateFigures:
    participant_count: int
    clusters: list[ClusterSupport]


def build_certificate_figures(
    model_run: ModelRun,
    votes_for_statement: list[tuple[int, int]],
) -> CertificateFigures:
    """Support inside every detected faction for one statement's votes.

    votes_for_statement is a list of (participant_id, value) pairs.
    Only participants the fit placed in a cluster are counted, since a
    faction assignment only exists for someone the model run covers.
    """
    vote_by_participant = dict(votes_for_statement)
    cluster_totals: dict[int, int] = {}
    cluster_agree: dict[int, int] = {}

    for participant_id_str, cluster in model_run.cluster_assignments.items():
        participant_id = int(participant_id_str)
        if participant_id not in vote_by_participant:
            continue
        cluster_totals[cluster] = cluster_totals.get(cluster, 0) + 1
        if vote_by_participant[participant_id] == 1:
            cluster_agree[cluster] = cluster_agree.get(cluster, 0) + 1

    clusters = [
        ClusterSupport(
            cluster=cluster,
            participant_count=total,
            agree_count=cluster_agree.get(cluster, 0),
            agree_fraction=(cluster_agree.get(cluster, 0) / total) if total else 0.0,
        )
        for cluster, total in sorted(cluster_totals.items())
    ]
    return CertificateFigures(
        participant_count=sum(cluster_totals.values()),
        clusters=clusters,
    )
