"""Tests for reply evaluation: batched engagement scoring and near
duplicate template detection scoped to one department.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine, select

from sabha.models import Clause, Consultation, Filing, FilingClauseLink, Reply
from sabha.services.quota import QuotaGuard
from sabha.services.reply_evaluation import (
    ReplyEvaluationParams,
    detect_template_replies,
    evaluate_reply_engagement,
)


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _consultation(session: Session) -> Consultation:
    now = datetime.now(UTC)
    consultation = Consultation(title="t", question="q", opens_at=now, closes_at=now)
    session.add(consultation)
    session.commit()
    session.refresh(consultation)
    return consultation


def _filing(session: Session, consultation_id: int, department: str) -> Filing:
    filing = Filing(
        consultation_id=consultation_id, department=department, channel="mock", artefact="a"
    )
    session.add(filing)
    session.commit()
    session.refresh(filing)
    return filing


def _clause(session: Session, consultation_id: int, model_run_id: int, text: str) -> Clause:
    clause = Clause(
        consultation_id=consultation_id, model_run_id=model_run_id, text=text,
        certificate_figures={},
    )
    session.add(clause)
    session.commit()
    session.refresh(clause)
    return clause


def _link(session: Session, filing_id: int, clause_id: int) -> None:
    session.add(FilingClauseLink(filing_id=filing_id, clause_id=clause_id))
    session.commit()


def _reply(
    session: Session, filing_id: int, text: str, engagement_score: float | None = None
) -> Reply:
    reply = Reply(filing_id=filing_id, received_text=text, engagement_score=engagement_score)
    session.add(reply)
    session.commit()
    session.refresh(reply)
    return reply


@dataclass
class _FakeGenerateResult:
    text: str | None


@dataclass
class _FakeEmbedding:
    values: list[float] | None


@dataclass
class _FakeEmbedResult:
    embeddings: list[_FakeEmbedding] | None


@dataclass
class _FakeModels:
    generate_text: str = "{}"
    vectors_by_text: dict[str, list[float]] = field(default_factory=dict)
    generate_calls: int = 0
    embed_calls: int = 0

    def generate_content(self, *, model: str, contents: str, config: object) -> _FakeGenerateResult:
        self.generate_calls += 1
        return _FakeGenerateResult(text=self.generate_text)

    def embed_content(self, *, model: str, contents: str) -> _FakeEmbedResult:
        self.embed_calls += 1
        vector = self.vectors_by_text[contents]
        return _FakeEmbedResult(embeddings=[_FakeEmbedding(values=vector)])


@dataclass
class _FakeClient:
    models: _FakeModels


# --- evaluate_reply_engagement --------------------------------------------------


def test_evaluate_reply_engagement_scores_only_unscored_replies() -> None:
    with _fresh_session() as session:
        consultation = _consultation(session)
        assert consultation.id is not None
        filing = _filing(session, consultation.id, "Ministry of Labour and Employment")
        assert filing.id is not None
        clause = _clause(session, consultation.id, 1, "Platforms shall pay a minimum hourly rate.")
        assert clause.id is not None
        _link(session, filing.id, clause.id)

        already_scored = _reply(session, filing.id, "We acknowledge receipt.", engagement_score=0.1)
        unscored = _reply(session, filing.id, "We accept the minimum hourly rate proposal.")

        response_json = (
            '{"judgements": ['
            f'{{"reply_id": {unscored.id}, "engagement_score": 0.85, '
            f'"rationale": "directly addresses the clause"}}'
            "]}"
        )
        fake = _FakeClient(models=_FakeModels(generate_text=response_json))
        quota = QuotaGuard(rpm=5, rpd=5)

        scored = evaluate_reply_engagement(
            session, quota, [already_scored, unscored], genai_client=fake
        )

        assert fake.models.generate_calls == 1
        assert len(scored) == 1
        assert scored[0].id == unscored.id
        assert scored[0].engagement_score == 0.85

        refreshed_already_scored = session.get(Reply, already_scored.id)
        assert refreshed_already_scored is not None
        assert refreshed_already_scored.engagement_score == 0.1


def test_evaluate_reply_engagement_makes_no_call_when_everything_is_scored() -> None:
    with _fresh_session() as session:
        consultation = _consultation(session)
        assert consultation.id is not None
        filing = _filing(session, consultation.id, "Ministry of Labour and Employment")
        assert filing.id is not None
        reply = _reply(session, filing.id, "already scored", engagement_score=0.5)

        fake = _FakeClient(models=_FakeModels())
        quota = QuotaGuard(rpm=5, rpd=5)

        scored = evaluate_reply_engagement(session, quota, [reply], genai_client=fake)

        assert scored == []
        assert fake.models.generate_calls == 0


# --- detect_template_replies -----------------------------------------------------


def test_detect_template_replies_clusters_near_duplicate_text_only() -> None:
    with _fresh_session() as session:
        consultation = _consultation(session)
        assert consultation.id is not None
        department = "Ministry of Electronics and Information Technology"
        filing_a = _filing(session, consultation.id, department)
        filing_b = _filing(session, consultation.id, department)
        filing_c = _filing(session, consultation.id, department)
        assert filing_a.id is not None
        assert filing_b.id is not None
        assert filing_c.id is not None

        template_text_1 = "Thank you for your submission. It is under review."
        template_text_2 = "Thank you for your submission. It is under review!"
        distinct_text = "We are convening a stakeholder consultation on platform work rules."

        _reply(session, filing_a.id, template_text_1)
        _reply(session, filing_b.id, template_text_2)
        _reply(session, filing_c.id, distinct_text)

        fake = _FakeClient(
            models=_FakeModels(
                vectors_by_text={
                    template_text_1: [1.0, 0.0, 0.0],
                    template_text_2: [0.99, 0.01, 0.0],
                    distinct_text: [0.0, 1.0, 0.0],
                }
            )
        )
        quota = QuotaGuard(rpm=5, rpd=5)

        assignments = detect_template_replies(session, quota, department, genai_client=fake)

        clustered_texts = {
            reply.received_text
            for reply in session.exec(select(Reply)).all()
            if reply.id in assignments
        }
        assert clustered_texts == {template_text_1, template_text_2}
        assert len(set(assignments.values())) == 1

        all_replies = session.exec(select(Reply)).all()
        unclustered = [r for r in all_replies if r.received_text == distinct_text]
        assert unclustered[0].template_cluster is None


def test_detect_template_replies_leaves_all_distinct_replies_unclustered() -> None:
    with _fresh_session() as session:
        consultation = _consultation(session)
        assert consultation.id is not None
        department = "Department of Consumer Affairs"
        filing_a = _filing(session, consultation.id, department)
        filing_b = _filing(session, consultation.id, department)
        assert filing_a.id is not None
        assert filing_b.id is not None

        _reply(session, filing_a.id, "first distinct reply")
        _reply(session, filing_b.id, "second distinct reply")

        fake = _FakeClient(
            models=_FakeModels(
                vectors_by_text={
                    "first distinct reply": [1.0, 0.0],
                    "second distinct reply": [0.0, 1.0],
                }
            )
        )
        quota = QuotaGuard(rpm=5, rpd=5)

        assignments = detect_template_replies(
            session, quota, department, params=ReplyEvaluationParams(), genai_client=fake
        )

        assert assignments == {}


def test_detect_template_replies_returns_empty_for_an_unknown_department() -> None:
    with _fresh_session() as session:
        fake = _FakeClient(models=_FakeModels())
        quota = QuotaGuard(rpm=5, rpd=5)

        assignments = detect_template_replies(
            session, quota, "Nonexistent Ministry", genai_client=fake
        )

        assert assignments == {}
        assert fake.models.embed_calls == 0
