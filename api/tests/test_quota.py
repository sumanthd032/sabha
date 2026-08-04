"""Tests for the Gemini free tier quota guard."""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from sabha.services.quota import QuotaExhaustedError, QuotaGuard


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_reserve_succeeds_within_both_limits() -> None:
    guard = QuotaGuard(rpm=5, rpd=20)
    with _fresh_session() as session:
        for _ in range(5):
            guard.reserve(session)
        assert guard.remaining_today(session) == 15


def test_reserve_raises_once_the_per_minute_limit_is_reached() -> None:
    guard = QuotaGuard(rpm=2, rpd=20)
    with _fresh_session() as session:
        guard.reserve(session)
        guard.reserve(session)
        with pytest.raises(QuotaExhaustedError):
            guard.reserve(session)


def test_reserve_raises_once_the_per_day_limit_is_reached() -> None:
    guard = QuotaGuard(rpm=100, rpd=3)
    with _fresh_session() as session:
        guard.reserve(session)
        guard.reserve(session)
        guard.reserve(session)
        with pytest.raises(QuotaExhaustedError):
            guard.reserve(session)
        assert guard.remaining_today(session) == 0


def test_a_failed_reservation_does_not_consume_the_daily_counter() -> None:
    guard = QuotaGuard(rpm=1, rpd=20)
    with _fresh_session() as session:
        guard.reserve(session)
        with pytest.raises(QuotaExhaustedError):
            guard.reserve(session)
        # the per-minute failure above must not have advanced the daily count
        assert guard.remaining_today(session) == 19


def test_the_daily_counter_persists_across_a_new_guard_instance() -> None:
    """A restarted process should not get a fresh daily budget."""
    with _fresh_session() as session:
        first_guard = QuotaGuard(rpm=100, rpd=20)
        for _ in range(5):
            first_guard.reserve(session)

        second_guard = QuotaGuard(rpm=100, rpd=20)
        assert second_guard.remaining_today(session) == 15
        second_guard.reserve(session)
        assert second_guard.remaining_today(session) == 14


def test_remaining_today_never_goes_negative() -> None:
    guard = QuotaGuard(rpm=100, rpd=1)
    with _fresh_session() as session:
        guard.reserve(session)
        with pytest.raises(QuotaExhaustedError):
            guard.reserve(session)
        assert guard.remaining_today(session) == 0
