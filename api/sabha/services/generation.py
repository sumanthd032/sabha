"""The generation loop: propose reformulations of divisive statements,
inject them into the live pool, and retire the ones that do not
measurably beat their parent.

Section 6.3 of the project description. Target selection looks for the
real fault lines: statements with a low bridging score mu(j) but a
large loading norm |g(j)|, meaning positions that matter enough to
split the room rather than ones nobody has an opinion on. The two
measures are on different scales, so targets are ranked by the sum of
each measure's own rank rather than a weighted combination of the raw
values.

Eligible targets are restricted to participant authored, approved
statements: the loop reformulates what people actually wrote, rather
than compounding reformulations of its own earlier output. A target
with a variant still awaiting its own significance test is excluded
from being targeted again until that round finishes, so a divisive
statement never accumulates two overlapping batches of children; once
evaluated, one way or the other, it is eligible again if it is still a
fault line.

Winners are decided by a two sample z-test on the fitted mu(j), not on
a raw vote tally: mu(j) is itself already a ridge shrunk estimate, and
comparing two point estimates on a handful of votes each would
manufacture progress the data does not support. The test reuses
statement_posterior_width from selection.py, the same ridge posterior
variance the adaptive selection policy is built on, so "does this
variant significantly beat its parent" and "how uncertain is this
statement's score" come from one consistent model rather than two. A
variant that does not clear the bar is retired rather than left in the
pool merely tied with its parent, so the pool's population only grows
by statements with demonstrated improvement, per the genetic algorithm
framing in section 6.3: fitness is measured human agreement.
"""

from dataclasses import dataclass

import numpy as np
from sqlmodel import Session, col, select

from sabha.llm.client import GenaiClient, call_structured, load_prompt
from sabha.llm.schemas import VariantBatch
from sabha.models import (
    AuthorType,
    Consultation,
    LedgerEntry,
    ModelRun,
    ModerationState,
    Statement,
    Vote,
)
from sabha.services.certificate import build_certificate_figures
from sabha.services.factorisation import FactorisationResult
from sabha.services.quota import QuotaGuard
from sabha.services.selection import statement_posterior_width


@dataclass(frozen=True)
class GenerationParams:
    max_targets_per_cycle: int = 3
    pool_fraction_cap: float = 0.2
    min_votes_for_evaluation: int = 20
    significance_z: float = 1.645
    accepted_sample_size: int = 2
    min_cluster_size_for_sample: int = 5


@dataclass(frozen=True)
class GenerationOutcome:
    variant_id: int
    parent_id: int
    retained: bool
    z_score: float
    variant_mu: float
    parent_mu: float


def _rank_best_first(values: np.ndarray) -> np.ndarray:
    """0 for the smallest value, ascending from there."""
    order = np.argsort(values)
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values))
    return ranks


def select_generation_targets(
    result: FactorisationResult,
    statements: dict[int, Statement],
    pending_children_by_parent: dict[int, int],
    generated_count: int,
    pool_size: int,
    params: GenerationParams,
) -> list[int]:
    """The targets for one generation cycle, best fault line first.

    Returns an empty list when the pool fraction cap leaves no room for
    even one full target's batch of four variants, so the caller can
    skip the language model call entirely rather than requesting a
    batch it would have to discard.
    """
    budget = int(params.pool_fraction_cap * pool_size) - generated_count
    max_targets = min(params.max_targets_per_cycle, budget // 4)
    if max_targets <= 0:
        return []

    fitted_ids = set(result.statement_ids)
    eligible = [
        sid
        for sid, statement in statements.items()
        if sid in fitted_ids
        and statement.author_type == AuthorType.PARTICIPANT
        and statement.moderation_state == ModerationState.APPROVED
        and pending_children_by_parent.get(sid, 0) == 0
    ]
    if not eligible:
        return []

    index = {sid: j for j, sid in enumerate(result.statement_ids)}
    mu_values = np.array([result.mu[index[sid]] for sid in eligible])
    loading_norms = np.array([float(np.linalg.norm(result.g[index[sid]])) for sid in eligible])

    combined = _rank_best_first(mu_values) + _rank_best_first(-loading_norms)
    order = np.argsort(combined)
    return [eligible[i] for i in order[:max_targets]]


def _vote_counts(session: Session, statement_ids: list[int]) -> dict[int, int]:
    if not statement_ids:
        return {}
    vote_rows = session.exec(select(Vote).where(col(Vote.statement_id).in_(statement_ids))).all()
    counts: dict[int, int] = {}
    for vote in vote_rows:
        counts[vote.statement_id] = counts.get(vote.statement_id, 0) + 1
    return counts


def _votes_by_statement(
    session: Session, statement_ids: list[int]
) -> dict[int, list[tuple[int, int]]]:
    if not statement_ids:
        return {}
    vote_rows = session.exec(select(Vote).where(col(Vote.statement_id).in_(statement_ids))).all()
    grouped: dict[int, list[tuple[int, int]]] = {}
    for vote in vote_rows:
        grouped.setdefault(vote.statement_id, []).append((vote.participant_id, vote.value))
    return grouped


def _accepted_by_cluster(
    model_run: ModelRun,
    statements: dict[int, Statement],
    votes_by_statement: dict[int, list[tuple[int, int]]],
    min_cluster_size: int,
) -> dict[int, list[Statement]]:
    """Per cluster, every statement it has voted on, best agreement
    first: what a cluster already accepts, for the prompt's context.
    """
    scored: dict[int, list[tuple[float, Statement]]] = {}
    for statement_id, statement in statements.items():
        figures = build_certificate_figures(model_run, votes_by_statement.get(statement_id, []))
        for cluster in figures.clusters:
            if cluster.participant_count < min_cluster_size:
                continue
            scored.setdefault(cluster.cluster, []).append((cluster.agree_fraction, statement))
    return {
        cluster: [stmt for _, stmt in sorted(items, key=lambda pair: pair[0], reverse=True)]
        for cluster, items in scored.items()
    }


def _format_targets_block(
    model_run: ModelRun,
    target_ids: list[int],
    statements: dict[int, Statement],
    votes_by_statement: dict[int, list[tuple[int, int]]],
    accepted_by_cluster: dict[int, list[Statement]],
    params: GenerationParams,
) -> str:
    blocks = []
    for target_id in target_ids:
        target = statements[target_id]
        figures = build_certificate_figures(model_run, votes_by_statement.get(target_id, []))
        lines = [f"Target statement id {target_id}:", f'"{target.text}"']
        for cluster in figures.clusters:
            lines.append(
                f"Cluster {cluster.cluster} (n={cluster.participant_count}): "
                f"{cluster.agree_fraction:.0%} agree"
            )
            samples = [
                s
                for s in accepted_by_cluster.get(cluster.cluster, [])
                if s.id != target_id
            ][: params.accepted_sample_size]
            if samples:
                texts = "; ".join(f'"{s.text}"' for s in samples)
                lines.append(f"Cluster {cluster.cluster} already accepts: {texts}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def prepare_generation_prompt(
    session: Session,
    consultation_id: int,
    model_run: ModelRun,
    result: FactorisationResult,
    params: GenerationParams | None = None,
) -> tuple[list[int], str, dict[int, Statement]] | None:
    """Select targets and render the batched prompt for one generation
    cycle, or None when there is nothing to generate: no eligible
    target, or no room left under the pool fraction cap. Callers must
    treat None as "make no call", not as an error.
    """
    params = params or GenerationParams()
    consultation = session.get(Consultation, consultation_id)
    assert consultation is not None

    statements = {
        s.id: s
        for s in session.exec(
            select(Statement).where(Statement.consultation_id == consultation_id)
        ).all()
        if s.id is not None
    }
    approved_statements = {
        sid: s for sid, s in statements.items() if s.moderation_state == ModerationState.APPROVED
    }
    pool_size = len(approved_statements)
    generated_count = sum(
        1 for s in approved_statements.values() if s.author_type == AuthorType.GENERATED
    )

    votes_by_statement = _votes_by_statement(session, list(statements.keys()))
    pending_children_by_parent: dict[int, int] = {}
    for statement_id, statement in approved_statements.items():
        if (
            statement.author_type == AuthorType.GENERATED
            and statement.parent_statement_id is not None
            and len(votes_by_statement.get(statement_id, [])) < params.min_votes_for_evaluation
        ):
            parent_id = statement.parent_statement_id
            pending_children_by_parent[parent_id] = pending_children_by_parent.get(parent_id, 0) + 1

    target_ids = select_generation_targets(
        result, approved_statements, pending_children_by_parent, generated_count, pool_size, params
    )
    if not target_ids:
        return None

    accepted_by_cluster = _accepted_by_cluster(
        model_run, approved_statements, votes_by_statement, params.min_cluster_size_for_sample
    )
    targets_block = _format_targets_block(
        model_run, target_ids, statements, votes_by_statement, accepted_by_cluster, params
    )
    prompt = load_prompt(
        "generate_variants", consultation_question=consultation.question, targets=targets_block
    )
    return target_ids, prompt, statements


def _next_statement_code_number(session: Session) -> int:
    codes = session.exec(select(Statement.code)).all()
    max_number = 0
    for code in codes:
        _, _, suffix = code.partition("-")
        if suffix.isdigit():
            max_number = max(max_number, int(suffix))
    return max_number + 1


def inject_variants(
    session: Session,
    consultation_id: int,
    statements: dict[int, Statement],
    batch: VariantBatch,
) -> list[Statement]:
    """Create one Statement row per proposed variant, generated and
    parented to its target, approved and immediately visible: a target
    is already something real participants are voting on, so its
    reformulations go straight into the same live pool per section 6.3.
    A freshly injected statement only joins the adaptive selection
    candidate pool at the next refit, per docs/api.md, since it has no
    fitted g(j) or mu(j) until then.
    """
    next_code_number = _next_statement_code_number(session)
    created: list[Statement] = []
    for target_variants in batch.target_variants:
        target = statements.get(target_variants.target_statement_id)
        if target is None:
            continue
        for variant in target_variants.variants:
            statement = Statement(
                consultation_id=consultation_id,
                code=f"S-{next_code_number:04d}",
                text=variant.text,
                language=target.language,
                author_type=AuthorType.GENERATED,
                parent_statement_id=target.id,
                moderation_state=ModerationState.APPROVED,
                is_synthetic=target.is_synthetic,
            )
            next_code_number += 1
            session.add(statement)
            created.append(statement)
    session.commit()
    for statement in created:
        session.refresh(statement)
    return created


def run_generation_cycle(
    session: Session,
    quota: QuotaGuard,
    consultation_id: int,
    model_run: ModelRun,
    result: FactorisationResult,
    params: GenerationParams | None = None,
    genai_client: GenaiClient | None = None,
) -> list[Statement]:
    """One generation cycle: select targets, request every target's
    variants in a single batched call, and inject the result.

    Returns an empty list, making no call and spending no quota, when
    prepare_generation_prompt finds nothing worth generating.
    """
    params = params or GenerationParams()
    prepared = prepare_generation_prompt(session, consultation_id, model_run, result, params)
    if prepared is None:
        return []
    target_ids, prompt, statements = prepared

    batch = call_structured(
        session, quota, prompt, VariantBatch, "VariantBatch", genai_client=genai_client
    )
    injectable = VariantBatch(
        target_variants=[tv for tv in batch.target_variants if tv.target_statement_id in target_ids]
    )
    return inject_variants(session, consultation_id, statements, injectable)


def evaluate_pending_variants(
    session: Session,
    consultation_id: int,
    result: FactorisationResult,
    params: GenerationParams | None = None,
) -> list[GenerationOutcome]:
    """Score every approved generated statement with enough votes to
    judge, against its parent, and retire the ones that do not clear
    the significance bar. Pure computation over an already fitted
    result: no language model call, so this runs on every refit rather
    than waiting for a human to ask for it.
    """
    params = params or GenerationParams()
    variants = {
        s.id: s
        for s in session.exec(
            select(Statement).where(
                Statement.consultation_id == consultation_id,
                Statement.author_type == AuthorType.GENERATED,
                Statement.moderation_state == ModerationState.APPROVED,
            )
        ).all()
        if s.id is not None
    }
    if not variants:
        return []

    fitted_ids = set(result.statement_ids)
    mu_by_id = result.mu_by_statement()
    relevant_ids = list(variants.keys()) + [
        s.parent_statement_id for s in variants.values() if s.parent_statement_id is not None
    ]
    vote_counts = _vote_counts(session, relevant_ids)

    outcomes: list[GenerationOutcome] = []
    for variant_id, variant in variants.items():
        parent_id = variant.parent_statement_id
        if parent_id is None or variant_id not in fitted_ids or parent_id not in fitted_ids:
            continue
        variant_votes = vote_counts.get(variant_id, 0)
        if variant_votes < params.min_votes_for_evaluation:
            continue
        parent_votes = vote_counts.get(parent_id, 0)

        variant_mu = mu_by_id[variant_id]
        parent_mu = mu_by_id[parent_id]
        variance = statement_posterior_width(
            variant_votes, result.params.lambda_intercept
        ) + statement_posterior_width(parent_votes, result.params.lambda_intercept)
        z = float((variant_mu - parent_mu) / np.sqrt(variance))
        retained = z > params.significance_z

        if not retained:
            variant.moderation_state = ModerationState.REJECTED
            session.add(variant)

        session.add(
            LedgerEntry(
                action="generation_variant_retained" if retained else "generation_variant_retired",
                reason=(
                    f"{variant.code} vs parent statement {parent_id}: z={z:.2f} "
                    f"(variant mu={variant_mu:.3f} n={variant_votes}, "
                    f"parent mu={parent_mu:.3f} n={parent_votes})"
                ),
                policy_state={
                    "z_score": z,
                    "significance_threshold": params.significance_z,
                    "variant_statement_id": variant_id,
                    "parent_statement_id": parent_id,
                    "variant_mu": variant_mu,
                    "parent_mu": parent_mu,
                    "variant_votes": variant_votes,
                    "parent_votes": parent_votes,
                },
                consultation_id=consultation_id,
            )
        )
        outcomes.append(
            GenerationOutcome(
                variant_id=variant_id,
                parent_id=parent_id,
                retained=retained,
                z_score=z,
                variant_mu=variant_mu,
                parent_mu=parent_mu,
            )
        )
    session.commit()
    return outcomes
