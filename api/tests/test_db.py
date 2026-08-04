"""Tests for the database URL normalisation that picks the psycopg
driver, since a bare postgresql:// URL from Neon otherwise resolves to
psycopg2, which this project never installs.
"""

from sabha.db import _with_psycopg_driver


def test_rewrites_a_bare_postgresql_url_to_use_psycopg() -> None:
    assert (
        _with_psycopg_driver("postgresql://user:pass@host/db")
        == "postgresql+psycopg://user:pass@host/db"
    )


def test_rewrites_the_postgres_scheme_some_providers_use() -> None:
    assert (
        _with_psycopg_driver("postgres://user:pass@host/db")
        == "postgresql+psycopg://user:pass@host/db"
    )


def test_leaves_a_url_that_already_names_a_driver_untouched() -> None:
    assert _with_psycopg_driver("postgresql+psycopg://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )


def test_leaves_a_sqlite_url_untouched() -> None:
    assert _with_psycopg_driver("sqlite:///./sabha.db") == "sqlite:///./sabha.db"
