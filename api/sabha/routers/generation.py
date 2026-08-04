"""The generation loop's single endpoint: run one cycle over the
current model run's fault lines and inject the resulting variants.

Evaluating a pending variant's significance test is not exposed here:
it costs no language model call, so it runs automatically on every
debounced refit in services/live.py rather than waiting on a human to
ask for it.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from sabha.config import settings
from sabha.db import get_session
from sabha.llm.client import GenaiClient, default_client
from sabha.routers.consultations import get_consultation_or_404
from sabha.schemas import GenerationRunOut, StatementOut
from sabha.services.generation import GenerationParams, run_generation_cycle
from sabha.services.model_run import latest_model_run, result_from_model_run
from sabha.services.quota import QuotaExhaustedError, QuotaGuard

router = APIRouter(prefix="/api/consultations/{consultation_id}", tags=["generation"])

_default_quota_guard = QuotaGuard(rpm=settings.quota_rpm, rpd=settings.quota_rpd)


def get_quota_guard() -> QuotaGuard:
    """The process-wide quota guard, overridden in tests."""
    return _default_quota_guard


def get_genai_client() -> GenaiClient:
    """The process-wide Gemini client, overridden in tests."""
    return default_client()


@router.post("/generation/run", response_model=GenerationRunOut)
def run_generation(
    consultation_id: int,
    session: Session = Depends(get_session),
    quota: QuotaGuard = Depends(get_quota_guard),
    genai_client: GenaiClient = Depends(get_genai_client),
) -> GenerationRunOut:
    """Select this consultation's current fault lines and, in a single
    batched call, propose and inject their reformulations.

    404 before the first model run: there is nothing to locate a fault
    line against yet. 503 when the quota guard has nothing left today,
    with the exact copy the interface shows for a paused generation.
    """
    get_consultation_or_404(consultation_id, session)
    model_run = latest_model_run(session, consultation_id)
    if model_run is None:
        raise HTTPException(status_code=404, detail="no model run yet for this consultation")
    result = result_from_model_run(model_run)

    try:
        injected = run_generation_cycle(
            session, quota, consultation_id, model_run, result, GenerationParams(), genai_client
        )
    except QuotaExhaustedError:
        raise HTTPException(
            status_code=503, detail="generation paused, daily quota reached"
        ) from None

    return GenerationRunOut(
        injected=[
            StatementOut(
                id=statement.id,
                code=statement.code,
                text=statement.text,
                language=statement.language,
                author_type=statement.author_type,
                parent_statement_id=statement.parent_statement_id,
                is_synthetic=statement.is_synthetic,
            )
            for statement in injected
            if statement.id is not None
        ]
    )
