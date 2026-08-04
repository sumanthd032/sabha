"""The escalation scheduler: what happens to a filing after it is
submitted, solved as optimal stopping.

Section 6.6 of the project description: filing immediately is wrong,
and waiting past the closing day is worse, because after filing the
question repeats every day, keep waiting, or escalate. This module
models a department's time to reply as a probability distribution
estimated from its own reply history, or a prior when it has none yet,
and solves for the day waiting stops paying for itself by backward
induction over a discretised horizon, small enough to be solved exactly
rather than approximated.

The Right to Information Act gives the concrete three stage structure
encoded here: thirty days for the department to reply, then a First
Appellate Authority, then the Information Commission. A filing moves
FILED -> AWAITING_REPLY -> ESCALATED_APPELLATE -> ESCALATED_COMMISSION
on this schedule's own decisions, to REPLIED the moment
services.filing.record_reply is called, whichever comes first, and to
CLOSED if the commission stage's own horizon runs out with no reply,
since there is nowhere further to escalate to.

Rate limiting per department and the demo's compressible clock are
both enforced in run_escalation_check, never left for a caller to
remember, per section 9.
"""

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from sabha.models import Filing, FilingStage, LedgerEntry, Reply
from sabha.services.ledger import record


@dataclass(frozen=True)
class EscalationParams:
    """Every tunable of the model, gathered in one place.

    escalation_effectiveness models the one real benefit of escalating:
    a higher authority can compel a reply a plain wait cannot. Each
    step multiplies the per day reply hazard by this factor, compounding
    at commission since it sits above the appellate authority in the
    same chain. Without it, escalating would only ever add
    escalate_step_cost for no benefit, because this build has no
    department history broken down by stage and would otherwise reuse
    the same hazard curve at every one.
    """

    awaiting_reply_horizon_days: int = 30
    appellate_horizon_days: int = 45
    commission_horizon_days: int = 180
    delay_cost_per_day: float = 1.0
    escalate_step_cost: float = 8.0
    unresolved_closure_cost: float = 16.0
    prior_mean_reply_days: float = 20.0
    escalation_effectiveness: float = 1.6


@dataclass(frozen=True)
class RateLimitParams:
    """Section 9: rate limits per department, enforced here, not merely
    recommended.
    """

    max_escalations_per_window: int = 3
    window_hours: float = 24.0


def _geometric_hazard(prior_mean_days: float, horizon: int) -> list[float]:
    """A constant per day reply probability implying the given mean time
    to reply, the fallback for a department with no reply history.
    """
    daily_probability = 1.0 / max(prior_mean_days, 1.0)
    return [min(daily_probability, 1.0)] * horizon


def _empirical_hazard(
    response_days: list[int], horizon: int, prior_mean_days: float
) -> list[float]:
    """hazard[t]: the probability a reply arrives on day t given none
    arrived through day t - 1, read off this department's own history.
    Falls back to _geometric_hazard when there is no history at all.
    """
    if not response_days:
        return _geometric_hazard(prior_mean_days, horizon)
    counts_on_day = [0] * horizon
    for day in response_days:
        if 0 <= day < horizon:
            counts_on_day[day] += 1
    survivors = len(response_days)
    hazard = []
    for t in range(horizon):
        hazard.append(counts_on_day[t] / survivors if survivors > 0 else 0.0)
        survivors -= counts_on_day[t]
    return hazard


def _scaled_hazard(hazard: list[float], multiplier: float) -> list[float]:
    """hazard scaled up by multiplier and clamped to a valid probability,
    escalation_effectiveness's mechanism for making a later stage
    genuinely more likely to end in a reply, not just more expensive.
    """
    return [min(h * multiplier, 1.0) for h in hazard]


def department_response_days(session: Session, department: str) -> list[int]:
    """Days between filing and reply for every replied filing this
    department has ever received, the empirical history the hazard is
    fitted to. Note this build only ever observes filing to reply
    latency, not which stage the reply arrived in, so the same history
    informs every stage's hazard below.
    """
    filings = session.exec(
        select(Filing)
        .where(Filing.department == department)
        .where(col(Filing.submitted_at).is_not(None))
    ).all()
    submitted_at_by_id = {f.id: f.submitted_at for f in filings if f.id is not None}
    if not submitted_at_by_id:
        return []
    replies = session.exec(
        select(Reply).where(col(Reply.filing_id).in_(submitted_at_by_id.keys()))
    ).all()
    days: list[int] = []
    for reply in replies:
        submitted_at = submitted_at_by_id[reply.filing_id]
        assert submitted_at is not None
        delta = reply.received_at - submitted_at
        days.append(max(0, delta.days))
    return days


def _backward_induction(
    hazard: list[float], delay_cost_per_day: float, escalate_cost: float, next_stage_value: float
) -> tuple[list[str], float]:
    """Solve one escalatable stage's stopping problem given the value of
    moving on to the next stage.

    Returns (policy, value_at_day_zero). policy[t] is "wait" or
    "escalate" for elapsed day t. value_at_day_zero feeds the previous
    stage's own next_stage_value, which is what chains the induction
    from the last stage backward to the first: value[horizon] is the
    forced boundary, waiting past the statutory deadline is never
    offered as a choice, so escalating there is the only cost, an exact
    discretised terminal condition rather than an approximation.
    """
    horizon = len(hazard)
    escalate_now_cost = escalate_cost + next_stage_value
    value = [0.0] * (horizon + 1)
    policy = ["wait"] * horizon
    value[horizon] = escalate_now_cost
    for t in range(horizon - 1, -1, -1):
        wait_cost = delay_cost_per_day + (1.0 - hazard[t]) * value[t + 1]
        if escalate_now_cost < wait_cost:
            value[t] = escalate_now_cost
            policy[t] = "escalate"
        else:
            value[t] = wait_cost
    return policy, value[0]


def _pure_wait_value(hazard: list[float], delay_cost_per_day: float, closure_cost: float) -> float:
    """The expected cost of a stage with no escalate action at all, the
    commission stage's own problem: wait every day until a reply
    arrives or the horizon forces closure.
    """
    value = closure_cost
    for t in range(len(hazard) - 1, -1, -1):
        value = delay_cost_per_day + (1.0 - hazard[t]) * value
    return value


@dataclass(frozen=True)
class EscalationPolicy:
    """One department's full policy: a wait or escalate decision per
    elapsed day, for each stage that still has somewhere to escalate
    to. The commission stage has nowhere further to escalate, so
    run_escalation_check reads its horizon straight from params
    instead of a policy table.
    """

    department: str
    params: EscalationParams
    awaiting_reply: list[str]
    appellate: list[str]

    def action_at(self, stage: FilingStage, elapsed_days: int) -> str:
        table = (
            self.awaiting_reply
            if stage in (FilingStage.FILED, FilingStage.AWAITING_REPLY)
            else self.appellate
        )
        index = min(max(elapsed_days, 0), len(table) - 1)
        return table[index]


def compute_escalation_policy(
    session: Session, department: str, params: EscalationParams | None = None
) -> EscalationPolicy:
    """Backward induction over the three RTI stages, chained from the
    commission stage back to the first day of awaiting reply.
    """
    params = params or EscalationParams()
    response_days = department_response_days(session, department)

    commission_hazard = _scaled_hazard(
        _empirical_hazard(
            response_days, params.commission_horizon_days, params.prior_mean_reply_days
        ),
        params.escalation_effectiveness**2,
    )
    commission_value = _pure_wait_value(
        commission_hazard, params.delay_cost_per_day, params.unresolved_closure_cost
    )

    appellate_hazard = _scaled_hazard(
        _empirical_hazard(
            response_days, params.appellate_horizon_days, params.prior_mean_reply_days
        ),
        params.escalation_effectiveness,
    )
    appellate_policy, appellate_value = _backward_induction(
        appellate_hazard, params.delay_cost_per_day, params.escalate_step_cost, commission_value
    )

    awaiting_hazard = _empirical_hazard(
        response_days, params.awaiting_reply_horizon_days, params.prior_mean_reply_days
    )
    awaiting_policy, _ = _backward_induction(
        awaiting_hazard, params.delay_cost_per_day, params.escalate_step_cost, appellate_value
    )

    return EscalationPolicy(
        department=department,
        params=params,
        awaiting_reply=awaiting_policy,
        appellate=appellate_policy,
    )


def _as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo on a round trip through the database; every
    timestamp this module persists is UTC by the models.py convention,
    so a naive value read back is always UTC, never local time.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def effective_elapsed_days(
    now: datetime, stage_entered_at: datetime, demo_clock_scale: float
) -> float:
    """Wall clock time since entering the current stage, scaled by the
    demo's compression factor. Scale 1 is real statutory days; a higher
    scale is the compressible clock section 4.2 and section 10.3
    specify, so an escalation that would otherwise take thirty real
    days fires within a five minute demo, and DEMO_CLOCK_SCALE is
    always shown in the ledger's policy_state so the compression is
    never silent.
    """
    real_days = (_as_utc(now) - _as_utc(stage_entered_at)).total_seconds() / 86400.0
    return max(0.0, real_days) * demo_clock_scale


def _stage_entered_at(session: Session, filing: Filing) -> datetime:
    """When filing entered its current stage, read from the ledger it
    wrote entering that stage, rather than a redundant column: the
    ledger is already the durable record of every transition.
    """
    assert filing.id is not None
    if filing.stage in (FilingStage.FILED, FilingStage.AWAITING_REPLY):
        assert filing.submitted_at is not None
        return filing.submitted_at
    last_transition = session.exec(
        select(LedgerEntry)
        .where(LedgerEntry.filing_id == filing.id)
        .where(col(LedgerEntry.action).like("escalated_to_%"))
        .order_by(col(LedgerEntry.occurred_at).desc())
    ).first()
    if last_transition is not None:
        return last_transition.occurred_at
    assert filing.submitted_at is not None
    return filing.submitted_at


def department_escalation_count_in_window(
    session: Session, department: str, now: datetime, window_hours: float
) -> int:
    """How many escalations this department has already had inside the
    trailing window, the count the rate limit checks against.
    """
    window_start = now - timedelta(hours=window_hours)
    filing_ids = session.exec(
        select(Filing.id).where(Filing.department == department)
    ).all()
    known_filing_ids = [fid for fid in filing_ids if fid is not None]
    if not known_filing_ids:
        return 0
    rows = session.exec(
        select(LedgerEntry)
        .where(col(LedgerEntry.filing_id).in_(known_filing_ids))
        .where(col(LedgerEntry.action).like("escalated_to_%"))
        .where(LedgerEntry.occurred_at >= window_start)
    ).all()
    return len(rows)


def _rate_limit_allows(
    session: Session, department: str, now: datetime, params: RateLimitParams
) -> bool:
    count = department_escalation_count_in_window(session, department, now, params.window_hours)
    return count < params.max_escalations_per_window


_NEXT_STAGE = {
    FilingStage.AWAITING_REPLY: FilingStage.ESCALATED_APPELLATE,
    FilingStage.ESCALATED_APPELLATE: FilingStage.ESCALATED_COMMISSION,
}


def run_escalation_check(
    session: Session,
    filing: Filing,
    policy: EscalationPolicy,
    demo_clock_scale: float = 1.0,
    rate_limit_params: RateLimitParams | None = None,
    now: datetime | None = None,
) -> Filing:
    """Apply one scheduling decision to filing: start its clock, wait,
    escalate, or close it unresolved.

    A no-op, returning filing unchanged, for any stage the scheduler
    has no decision left to make: DRAFTED (not filed yet), REPLIED, or
    already CLOSED.
    """
    rate_limit_params = rate_limit_params or RateLimitParams()
    now = now or datetime.now(UTC)

    if filing.stage == FilingStage.FILED:
        filing.stage = FilingStage.AWAITING_REPLY
        session.add(filing)
        session.commit()
        session.refresh(filing)
        record(
            session,
            action="awaiting_reply_started",
            reason=f"statutory reply clock started for {filing.department}",
            policy_state={
                "statutory_deadline": (
                    filing.statutory_deadline.isoformat() if filing.statutory_deadline else None
                )
            },
            filing_id=filing.id,
            consultation_id=filing.consultation_id,
        )

    if filing.stage not in (
        FilingStage.AWAITING_REPLY,
        FilingStage.ESCALATED_APPELLATE,
        FilingStage.ESCALATED_COMMISSION,
    ):
        return filing

    stage_entered_at = _stage_entered_at(session, filing)
    elapsed = effective_elapsed_days(now, stage_entered_at, demo_clock_scale)

    if filing.stage == FilingStage.ESCALATED_COMMISSION:
        if elapsed < policy.params.commission_horizon_days:
            return filing
        filing.stage = FilingStage.CLOSED
        session.add(filing)
        session.commit()
        session.refresh(filing)
        record(
            session,
            action="filing_closed_unresolved",
            reason=f"{filing.department} did not reply through the commission stage",
            policy_state={"elapsed_effective_days": elapsed, "demo_clock_scale": demo_clock_scale},
            filing_id=filing.id,
            consultation_id=filing.consultation_id,
        )
        return filing

    action = policy.action_at(filing.stage, int(elapsed))
    if action == "wait":
        return filing

    if not _rate_limit_allows(session, filing.department, now, rate_limit_params):
        record(
            session,
            action="escalation_deferred_rate_limit",
            reason=f"{filing.department} is already at its escalation rate limit",
            policy_state={
                "window_hours": rate_limit_params.window_hours,
                "max_escalations_per_window": rate_limit_params.max_escalations_per_window,
            },
            filing_id=filing.id,
            consultation_id=filing.consultation_id,
        )
        return filing

    next_stage = _NEXT_STAGE[filing.stage]
    filing.stage = next_stage
    session.add(filing)
    session.commit()
    session.refresh(filing)
    record(
        session,
        action=f"escalated_to_{next_stage.value}",
        reason=f"{filing.department} did not reply within the modelled window",
        policy_state={"elapsed_effective_days": elapsed, "demo_clock_scale": demo_clock_scale},
        filing_id=filing.id,
        consultation_id=filing.consultation_id,
    )
    return filing


_OPEN_STAGES = (
    FilingStage.FILED, FilingStage.AWAITING_REPLY,
    FilingStage.ESCALATED_APPELLATE, FilingStage.ESCALATED_COMMISSION,
)


def run_escalation_sweep(
    session: Session,
    demo_clock_scale: float = 1.0,
    params: EscalationParams | None = None,
    rate_limit_params: RateLimitParams | None = None,
    now: datetime | None = None,
) -> list[Filing]:
    """Apply run_escalation_check to every open filing, computing each
    distinct department's policy once even when it has many filings.
    """
    now = now or datetime.now(UTC)
    open_filings = list(
        session.exec(select(Filing).where(col(Filing.stage).in_(_OPEN_STAGES))).all()
    )
    policies_by_department: dict[str, EscalationPolicy] = {}
    updated: list[Filing] = []
    for filing in open_filings:
        policy = policies_by_department.get(filing.department)
        if policy is None:
            policy = compute_escalation_policy(session, filing.department, params)
            policies_by_department[filing.department] = policy
        updated.append(
            run_escalation_check(
                session, filing, policy,
                demo_clock_scale=demo_clock_scale, rate_limit_params=rate_limit_params, now=now,
            )
        )
    return updated


class EscalationScheduler:
    """The process wide background loop that ticks run_escalation_sweep
    on a fixed interval, so escalation is genuinely autonomous rather
    than waiting on a human to poll an endpoint. It runs the sweep in a
    worker thread on its own session, the same reasoning
    services/live.py's refit uses: a session is not safe to share with
    a request thread, and the event loop should stay free to answer
    requests while the sweep runs.
    """

    def __init__(
        self, engine: Engine, interval_seconds: float = 5.0, demo_clock_scale: float = 1.0
    ) -> None:
        self._engine = engine
        self._interval_seconds = interval_seconds
        self._demo_clock_scale = demo_clock_scale
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            await asyncio.to_thread(self._sweep_once)

    def _sweep_once(self) -> None:
        with Session(self._engine) as session:
            run_escalation_sweep(session, demo_clock_scale=self._demo_clock_scale)
