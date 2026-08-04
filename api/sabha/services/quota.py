"""The Gemini free tier quota guard, exactly as specified in section 4.2:
a token bucket for the per-minute limit, and a persisted counter for
the per-day limit, both consulted before any call in llm/client.py
ever reaches the network.
"""

import threading
from collections import deque
from datetime import UTC, datetime

from sqlmodel import Session, select

from sabha.models import QuotaUsage


class QuotaExhaustedError(Exception):
    """Raised when neither the per-minute nor the per-day budget has
    room. Callers catch this to pause generation visibly, per section
    4.2: never fail silently, and never retry into a rate limit.
    """


def _today_key(now: datetime) -> str:
    return now.date().isoformat()


class QuotaGuard:
    """Not safe to share across processes: the per-minute bucket lives
    in this instance's memory, since a minute's window resets on its
    own regardless of restarts. The per-day counter is persisted, so it
    survives a restart within the same day, and a fresh QuotaGuard
    picks up wherever the last one left off.
    """

    def __init__(self, rpm: int, rpd: int) -> None:
        self._rpm = rpm
        self._rpd = rpd
        self._minute_window: deque[datetime] = deque()
        self._lock = threading.Lock()

    def _minute_capacity_available(self, now: datetime) -> bool:
        while self._minute_window and (now - self._minute_window[0]).total_seconds() >= 60:
            self._minute_window.popleft()
        return len(self._minute_window) < self._rpm

    def reserve(self, session: Session) -> None:
        """Reserve one request's worth of quota, or raise
        QuotaExhaustedError before any network call is attempted.
        """
        now = datetime.now(UTC)
        with self._lock:
            if not self._minute_capacity_available(now):
                raise QuotaExhaustedError("per-minute quota reached")

            day = _today_key(now)
            usage = session.exec(select(QuotaUsage).where(QuotaUsage.day == day)).first()
            if usage is None:
                usage = QuotaUsage(day=day, request_count=0)
                session.add(usage)
                session.flush()
            if usage.request_count >= self._rpd:
                raise QuotaExhaustedError("daily quota reached")

            usage.request_count += 1
            session.add(usage)
            session.commit()
            self._minute_window.append(now)

    def remaining_today(self, session: Session) -> int:
        usage = session.exec(
            select(QuotaUsage).where(QuotaUsage.day == _today_key(datetime.now(UTC)))
        ).first()
        used = usage.request_count if usage is not None else 0
        return max(0, self._rpd - used)
