"""Database engine and session management.

One engine for the process, built from DATABASE_URL: a SQLite file
locally, Postgres through psycopg in production. SQLite needs
check_same_thread disabled because FastAPI may serve a request on a
different thread than the one that opened the connection; Postgres
needs no such override.
"""

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from sabha.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)


def init_db() -> None:
    """Create every table that does not already exist."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Yield a session scoped to one request."""
    with Session(engine) as session:
        yield session
