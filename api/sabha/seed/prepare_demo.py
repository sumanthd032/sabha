"""Pre-generates and caches every language model response the demo
needs, per section 4.2's requirement that the live run make at most
one API call, and leaves the database in an already interesting state
per section 10's "seeded snapshot the demo loads from".

Run with `make prepare-demo`, pointed at DATABASE_URL for whichever
database the demo will actually run against. There is no separate
snapshot file: a Neon database persists, so the database this script
populates is the snapshot the live demo loads from.

Idempotent by construction. Seeding is skipped once a consultation
already exists, and every language model and embedding call underneath
this is cached by content hash, so running this twice costs no
additional quota and leaves the database exactly as it was.
"""

from sqlmodel import Session, select

from sabha.config import settings
from sabha.db import engine, init_db
from sabha.llm.client import default_client
from sabha.models import Consultation
from sabha.seed.allocation_rules import load_allocation_rules
from sabha.seed.loader import load_seed
from sabha.services.clause_drafting import ClauseDraftingParams, draft_clauses
from sabha.services.factorisation import FactorisationParams
from sabha.services.filing import MockFilingChannel, department_has_prior_filing, file_clause_set
from sabha.services.generation import (
    GenerationParams,
    evaluate_pending_variants,
    run_generation_cycle,
)
from sabha.services.model_run import fit_and_persist, result_from_model_run
from sabha.services.quota import QuotaGuard
from sabha.services.routing import RoutingParams, route_clauses

DEMO_FILING_DEPARTMENT = "Ministry of Labour and Employment"


def main() -> None:
    init_db()
    genai_client = default_client()
    quota = QuotaGuard(rpm=settings.quota_rpm, rpd=settings.quota_rpd)

    with Session(engine) as session:
        consultation = session.exec(select(Consultation)).first()
        if consultation is None:
            load_seed(session, num_participants=300, seed=7)
            consultation = session.exec(select(Consultation)).first()
        assert consultation is not None and consultation.id is not None
        consultation_id = consultation.id

        model_run = fit_and_persist(session, consultation_id, FactorisationParams())
        result = result_from_model_run(model_run)

        run_generation_cycle(
            session, quota, consultation_id, model_run, result, GenerationParams(), genai_client
        )

        model_run = fit_and_persist(session, consultation_id, FactorisationParams())
        result = result_from_model_run(model_run)
        evaluate_pending_variants(session, consultation_id, result)

        load_allocation_rules(session, quota, genai_client=genai_client)

        clauses = draft_clauses(
            session, quota, consultation_id, model_run, result, ClauseDraftingParams(), genai_client
        )
        route_clauses(session, quota, clauses, RoutingParams(), genai_client)

        filed_clause_ids = [clause.id for clause in clauses[:1] if clause.id is not None]
        already_filed = department_has_prior_filing(session, DEMO_FILING_DEPARTMENT)
        if filed_clause_ids and not already_filed:
            channel = MockFilingChannel()
            file_clause_set(
                session, consultation_id, DEMO_FILING_DEPARTMENT, filed_clause_ids,
                channel, confirmed_new_department=True,
            )

    print(f"demo preparation complete for consultation {consultation_id}")


if __name__ == "__main__":
    main()
