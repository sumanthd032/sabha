"""Reply evaluation: score whether a department's reply engaged with
the clauses it was filed against, and detect templated replies sent
across unrelated filings from the same department.

Section 6.7 of the project description. Substantive engagement is a
model judgement, batched across every unscored reply in one call,
since the stakes of a wrong call are low and the output is advisory
rather than filed anywhere. Template detection is the opposite kind of
task and is deliberately not a model call at all: it is a near
duplicate detection problem over reply text embeddings, solved the
same way coordination.py finds a voting bloc, connected components
over a thresholded similarity graph, because a template reveals itself
as a tight cluster of near identical text sent to unrelated filings
and that is exactly the shape single link clustering finds. An
individual citizen cannot see this pattern from one reply; a platform
holding many departments' replies can see nothing else.
"""

from dataclasses import dataclass

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from sqlmodel import Session, col, select

from sabha.llm.client import GenaiClient, call_embedding, call_structured, load_prompt
from sabha.llm.schemas import ReplyJudgementBatch
from sabha.models import Clause, Filing, FilingClauseLink, Reply
from sabha.services.quota import QuotaGuard


@dataclass(frozen=True)
class ReplyEvaluationParams:
    similarity_threshold: float = 0.92
    min_cluster_size: int = 2


def _clauses_for_filing(session: Session, filing_id: int) -> list[Clause]:
    clause_ids = session.exec(
        select(FilingClauseLink.clause_id).where(FilingClauseLink.filing_id == filing_id)
    ).all()
    if not clause_ids:
        return []
    return list(session.exec(select(Clause).where(col(Clause.id).in_(clause_ids))).all())


def _format_replies_block(replies: list[Reply], clauses_by_reply: dict[int, list[Clause]]) -> str:
    blocks = []
    for reply in replies:
        assert reply.id is not None
        clause_lines = "\n".join(f'- "{clause.text}"' for clause in clauses_by_reply[reply.id])
        blocks.append(
            f"Reply id {reply.id}:\nClauses submitted:\n{clause_lines}\n"
            f'Received reply:\n"{reply.received_text}"'
        )
    return "\n\n".join(blocks)


def evaluate_reply_engagement(
    session: Session,
    quota: QuotaGuard,
    replies: list[Reply],
    genai_client: GenaiClient | None = None,
) -> list[Reply]:
    """Score every not yet scored reply's engagement_score, batched into
    one call. A reply that already carries a score is left alone: a
    persisted judgement is not silently overwritten by a rerun.

    Makes no call, spending no quota, if every given reply is already
    scored.
    """
    unscored = [reply for reply in replies if reply.engagement_score is None]
    if not unscored:
        return []

    clauses_by_reply: dict[int, list[Clause]] = {}
    for reply in unscored:
        assert reply.id is not None
        clauses_by_reply[reply.id] = _clauses_for_filing(session, reply.filing_id)

    replies_block = _format_replies_block(unscored, clauses_by_reply)
    prompt = load_prompt("evaluate_reply", replies=replies_block)
    batch = call_structured(
        session, quota, prompt, ReplyJudgementBatch, "ReplyJudgementBatch",
        genai_client=genai_client,
    )

    by_id = {reply.id: reply for reply in unscored}
    scored: list[Reply] = []
    for judgement in batch.judgements:
        matched_reply = by_id.get(judgement.reply_id)
        if matched_reply is None:
            continue
        matched_reply.engagement_score = max(0.0, min(1.0, judgement.engagement_score))
        session.add(matched_reply)
        scored.append(matched_reply)

    session.commit()
    for reply in scored:
        session.refresh(reply)
    return scored


def detect_template_replies(
    session: Session,
    quota: QuotaGuard,
    department: str,
    params: ReplyEvaluationParams | None = None,
    genai_client: GenaiClient | None = None,
) -> dict[int, str]:
    """Cluster this department's replies by near duplicate text and
    persist the cluster label onto every reply placed in a cluster of
    at least min_cluster_size.

    Returns the assignments made. A reply whose text is not near
    duplicated by anything else from this department keeps
    template_cluster at None and is left out of the return value: not
    every reply belongs to a template, and most should not.
    """
    params = params or ReplyEvaluationParams()
    filing_ids = session.exec(select(Filing.id).where(Filing.department == department)).all()
    if not filing_ids:
        return {}
    replies = list(session.exec(select(Reply).where(col(Reply.filing_id).in_(filing_ids))).all())
    if len(replies) < params.min_cluster_size:
        return {}

    vectors = np.array(
        [
            call_embedding(session, quota, reply.received_text, genai_client=genai_client)
            for reply in replies
        ]
    )
    normed = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    similarity = normed @ normed.T
    adjacency = sparse.csr_matrix(similarity >= params.similarity_threshold)
    _, labels = connected_components(adjacency, directed=False)

    cluster_sizes: dict[int, int] = {}
    for label in labels:
        cluster_sizes[int(label)] = cluster_sizes.get(int(label), 0) + 1

    assignments: dict[int, str] = {}
    for reply, label in zip(replies, labels, strict=True):
        if cluster_sizes[int(label)] < params.min_cluster_size:
            continue
        assert reply.id is not None
        cluster_key = f"{department}-{label}"
        reply.template_cluster = cluster_key
        session.add(reply)
        assignments[reply.id] = cluster_key

    session.commit()
    return assignments
