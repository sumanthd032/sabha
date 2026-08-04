"""Tests for the escalation scheduler: backward induction, the
compressible clock, the department rate limit, and filing transitions.
"""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from sabha.models import Filing, FilingStage, LedgerEntry, Reply
from sabha.services.escalation import (
    EscalationParams,
    EscalationPolicy,
    RateLimitParams,
    compute_escalation_policy,
    department_escalation_count_in_window,
    department_response_days,
    effective_elapsed_days,
    run_escalation_check,
    run_escalation_sweep,
)
from sabha.services.ledger import ledger_for_consultation, record

DEPARTMENT = "Ministry of Labour and Employment"


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _filed_filing(
    session: Session,
    stage: FilingStage = FilingStage.FILED,
    submitted_at: datetime | None = None,
    department: str = DEPARTMENT,
) -> Filing:
    submitted_at = submitted_at or datetime.now(UTC)
    filing = Filing(
        consultation_id=1, department=department, channel="mock", artefact="MOCK-000001",
        stage=stage, submitted_at=submitted_at,
        statutory_deadline=submitted_at + timedelta(days=30),
    )
    session.add(filing)
    session.commit()
    session.refresh(filing)
    return filing


def _wait_policy(params: EscalationParams | None = None) -> EscalationPolicy:
    params = params or EscalationParams()
    return EscalationPolicy(
        department=DEPARTMENT, params=params,
        awaiting_reply=["wait"] * params.awaiting_reply_horizon_days,
        appellate=["wait"] * params.appellate_horizon_days,
    )


def _escalate_policy(params: EscalationParams | None = None) -> EscalationPolicy:
    params = params or EscalationParams()
    return EscalationPolicy(
        department=DEPARTMENT, params=params,
        awaiting_reply=["escalate"] * params.awaiting_reply_horizon_days,
        appellate=["escalate"] * params.appellate_horizon_days,
    )


def test_zero_delay_cost_never_escalates_before_the_horizon() -> None:
    with _fresh_session() as session:
        policy = compute_escalation_policy(
            session, DEPARTMENT, EscalationParams(delay_cost_per_day=0.0)
        )

        assert all(action == "wait" for action in policy.awaiting_reply)
        assert all(action == "wait" for action in policy.appellate)


def test_high_delay_cost_escalates_from_day_zero() -> None:
    with _fresh_session() as session:
        policy = compute_escalation_policy(
            session, DEPARTMENT, EscalationParams(delay_cost_per_day=1000.0, escalate_step_cost=1.0)
        )

        assert policy.awaiting_reply[0] == "escalate"


def test_compute_escalation_policy_falls_back_to_the_prior_with_no_history() -> None:
    with _fresh_session() as session:
        assert department_response_days(session, DEPARTMENT) == []

        policy = compute_escalation_policy(session, DEPARTMENT)

        assert len(policy.awaiting_reply) == EscalationParams().awaiting_reply_horizon_days


def test_department_response_days_reads_filing_to_reply_latency() -> None:
    with _fresh_session() as session:
        filed_at = datetime(2026, 1, 1, tzinfo=UTC)
        filing = _filed_filing(session, submitted_at=filed_at)
        session.add(
            Reply(
                filing_id=filing.id, received_text="ack",
                received_at=filed_at + timedelta(days=12),
            )
        )
        session.commit()

        assert department_response_days(session, DEPARTMENT) == [12]


def test_effective_elapsed_days_scales_with_the_demo_clock() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    now = start + timedelta(hours=12)

    assert effective_elapsed_days(now, start, demo_clock_scale=1.0) == 0.5
    assert effective_elapsed_days(now, start, demo_clock_scale=4.0) == 2.0


def test_run_escalation_check_starts_the_clock_on_first_tick() -> None:
    with _fresh_session() as session:
        filing = _filed_filing(session)
        assert filing.submitted_at is not None

        updated = run_escalation_check(session, filing, _wait_policy(), now=filing.submitted_at)

        assert updated.stage == FilingStage.AWAITING_REPLY
        entries = ledger_for_consultation(session, 1)
        assert entries[-1].action == "awaiting_reply_started"


def test_run_escalation_check_waits_when_the_policy_says_wait() -> None:
    with _fresh_session() as session:
        filing = _filed_filing(session, stage=FilingStage.AWAITING_REPLY)
        assert filing.submitted_at is not None

        updated = run_escalation_check(session, filing, _wait_policy(), now=filing.submitted_at)

        assert updated.stage == FilingStage.AWAITING_REPLY
        assert ledger_for_consultation(session, 1) == []


def test_run_escalation_check_escalates_to_appellate() -> None:
    with _fresh_session() as session:
        filing = _filed_filing(session, stage=FilingStage.AWAITING_REPLY)
        assert filing.submitted_at is not None

        updated = run_escalation_check(session, filing, _escalate_policy(), now=filing.submitted_at)

        assert updated.stage == FilingStage.ESCALATED_APPELLATE
        entries = ledger_for_consultation(session, 1)
        assert entries[-1].action == "escalated_to_escalated_appellate"


def test_run_escalation_check_escalates_to_commission() -> None:
    with _fresh_session() as session:
        filing = _filed_filing(session, stage=FilingStage.ESCALATED_APPELLATE)
        assert filing.submitted_at is not None

        updated = run_escalation_check(session, filing, _escalate_policy(), now=filing.submitted_at)

        assert updated.stage == FilingStage.ESCALATED_COMMISSION
        entries = ledger_for_consultation(session, 1)
        assert entries[-1].action == "escalated_to_escalated_commission"


def test_run_escalation_check_closes_unresolved_after_the_commission_horizon() -> None:
    with _fresh_session() as session:
        filing = _filed_filing(session, stage=FilingStage.ESCALATED_COMMISSION)
        assert filing.submitted_at is not None
        params = EscalationParams()
        past_horizon = filing.submitted_at + timedelta(days=params.commission_horizon_days + 1)

        updated = run_escalation_check(session, filing, _wait_policy(params), now=past_horizon)

        assert updated.stage == FilingStage.CLOSED
        entries = ledger_for_consultation(session, 1)
        assert entries[-1].action == "filing_closed_unresolved"


def test_run_escalation_check_stays_open_before_the_commission_horizon() -> None:
    with _fresh_session() as session:
        filing = _filed_filing(session, stage=FilingStage.ESCALATED_COMMISSION)
        assert filing.submitted_at is not None

        updated = run_escalation_check(
            session, filing, _wait_policy(), now=filing.submitted_at + timedelta(days=5)
        )

        assert updated.stage == FilingStage.ESCALATED_COMMISSION


def test_run_escalation_check_defers_when_the_department_is_rate_limited() -> None:
    with _fresh_session() as session:
        prior_filing = _filed_filing(session)
        record(
            session, action="escalated_to_escalated_appellate", reason="prior escalation",
            policy_state={}, filing_id=prior_filing.id, consultation_id=1,
        )

        filing = _filed_filing(session, stage=FilingStage.AWAITING_REPLY)
        assert filing.submitted_at is not None
        rate_limit = RateLimitParams(max_escalations_per_window=1, window_hours=24.0)

        updated = run_escalation_check(
            session, filing, _escalate_policy(),
            rate_limit_params=rate_limit, now=filing.submitted_at,
        )

        assert updated.stage == FilingStage.AWAITING_REPLY
        entries = ledger_for_consultation(session, 1)
        assert entries[-1].action == "escalation_deferred_rate_limit"


def test_department_escalation_count_in_window_ignores_entries_outside_the_window() -> None:
    with _fresh_session() as session:
        filing = _filed_filing(session)
        session.add(
            LedgerEntry(
                action="escalated_to_escalated_appellate", reason="old", policy_state={},
                filing_id=filing.id, consultation_id=1,
                occurred_at=datetime.now(UTC) - timedelta(days=10),
            )
        )
        session.commit()

        count = department_escalation_count_in_window(
            session, DEPARTMENT, datetime.now(UTC), window_hours=24.0
        )

        assert count == 0


def test_run_escalation_sweep_advances_every_open_filing() -> None:
    with _fresh_session() as session:
        _filed_filing(session)
        _filed_filing(session, department="Ministry of Electronics and Information Technology")

        updated = run_escalation_sweep(session, now=datetime.now(UTC))

        assert len(updated) == 2
        assert all(filing.stage == FilingStage.AWAITING_REPLY for filing in updated)


def test_run_escalation_sweep_returns_empty_for_no_open_filings() -> None:
    with _fresh_session() as session:
        assert run_escalation_sweep(session) == []
