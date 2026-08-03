"""Data behind the opinion map: each participant's fitted position and
faction, read directly off a model run snapshot.

Section 5.6 of the build instructions: the map positions and rotates a
tally stroke per participant by their fitted factor. Clustering is a
display convenience over that same fit, per factorisation.py's own
docstring, so this module only ever reads a model run, never refits.
"""

from dataclasses import dataclass

from sabha.models import ModelRun


@dataclass(frozen=True)
class ParticipantPoint:
    participant_id: int
    factor: tuple[float, float]
    cluster: int
    is_self: bool


def build_opinion_map(
    model_run: ModelRun, self_participant_id: int | None
) -> list[ParticipantPoint]:
    """One point per participant in the fitted model run.

    Only the first two dimensions of f(i) are used for position: the
    opinion map is always a two dimensional plot, regardless of how
    many factors a given fit used.
    """
    points = []
    for participant_id_str, factor in model_run.participant_factors.items():
        participant_id = int(participant_id_str)
        cluster = model_run.cluster_assignments.get(participant_id_str, 0)
        x = factor[0] if len(factor) > 0 else 0.0
        y = factor[1] if len(factor) > 1 else 0.0
        points.append(
            ParticipantPoint(
                participant_id=participant_id,
                factor=(x, y),
                cluster=cluster,
                is_self=participant_id == self_participant_id,
            )
        )
    return points
