"""Loads the synthetic seed corpus and synthetic votes into the database.

Everything this writes is marked is_synthetic=True on the consultation,
every statement, and every participant, so a reader querying the data
directly, not just looking at the interface, can tell it was never
collected from a real person.
"""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from sabha.models import Consultation, Participant, Statement, Vote
from sabha.seed.generator import GeneratedCorpus, generate_corpus
from sabha.seed.statements import CONSULTATION_QUESTION, CONSULTATION_TITLE, STATEMENTS


def load_seed(session: Session, num_participants: int = 300, seed: int = 0) -> dict[str, int]:
    """Insert one synthetic consultation with its statements, participants, and votes.

    Returns a count of each table's rows written, so a caller, whether a
    test or the loader script's own printout, can confirm what landed
    without a separate query.
    """
    now = datetime.now(UTC)
    consultation = Consultation(
        title=CONSULTATION_TITLE,
        question=CONSULTATION_QUESTION,
        is_synthetic=True,
        opens_at=now,
        closes_at=now + timedelta(days=30),
    )
    session.add(consultation)
    session.flush()
    assert consultation.id is not None

    statement_rows = []
    for index, seed_statement in enumerate(STATEMENTS, start=1):
        row = Statement(
            consultation_id=consultation.id,
            code=f"S-{index:04d}",
            text=seed_statement.text,
            language=seed_statement.language,
            is_synthetic=True,
        )
        session.add(row)
        statement_rows.append(row)
    session.flush()
    for row in statement_rows:
        assert row.id is not None

    corpus: GeneratedCorpus = generate_corpus(num_participants=num_participants, seed=seed)

    participant_rows = []
    for index, synthetic_participant in enumerate(corpus.participants):
        participant_row = Participant(
            consultation_id=consultation.id,
            session_token=f"synthetic-{seed}-{index:05d}",
            is_synthetic=True,
            planted_factor=synthetic_participant.factor.tolist(),
            planted_cluster=synthetic_participant.faction,
        )
        session.add(participant_row)
        participant_rows.append(participant_row)
    session.flush()
    for participant_row in participant_rows:
        assert participant_row.id is not None

    for p_index, s_index, value in corpus.votes:
        participant_row = participant_rows[p_index]
        statement_row = statement_rows[s_index]
        assert participant_row.id is not None
        assert statement_row.id is not None
        session.add(
            Vote(participant_id=participant_row.id, statement_id=statement_row.id, value=value)
        )
    session.commit()

    return {
        "consultations": 1,
        "statements": len(statement_rows),
        "participants": len(participant_rows),
        "votes": len(corpus.votes),
    }


def main() -> None:
    """Create the schema if needed and load the seed corpus once."""
    from sabha.db import engine, init_db

    init_db()
    with Session(engine) as session:
        counts = load_seed(session)
    print(f"loaded synthetic seed: {counts}")


if __name__ == "__main__":
    main()
