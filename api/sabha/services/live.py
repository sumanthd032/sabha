"""In-memory live session state: WebSocket fan-out and debounced refit.

A refit does not run on every vote; fifty participants voting in the
same second would otherwise trigger fifty alternating least squares
passes back to back. A vote instead (re)schedules a single timer per
consultation, cancelling whichever timer was already waiting, so only
the last vote in a burst actually starts a refit. That refit runs in a
worker thread so the event loop keeps answering join, vote, and
statement requests while it computes, which is what keeps a burst of
concurrent votes from stalling on each other.

The manager holds a live registry of WebSocket connections in process
memory, not in the database: a connection is only ever meaningful to
the process holding its socket, and there is exactly one such process
in this deployment.
"""

import asyncio
from collections.abc import Iterable

from fastapi import WebSocket
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from sabha.models import Statement, Vote
from sabha.services.factorisation import FactorisationParams
from sabha.services.model_run import fit_and_persist, result_from_model_run
from sabha.services.rankings import RankedStatement, build_rankings

DEBOUNCE_SECONDS = 2.0


def _serialise(entries: Iterable[RankedStatement]) -> list[dict[str, object]]:
    return [
        {
            "statement_id": entry.statement_id,
            "code": entry.code,
            "text": entry.text,
            "score": entry.score,
            "rank": entry.rank,
        }
        for entry in entries
    ]


class LiveSessionManager:
    """One instance is shared by the vote endpoint and the WebSocket route,
    so a vote taken through the REST API reaches everyone connected to
    that consultation's live channel.
    """

    def __init__(self, engine: Engine, debounce_seconds: float = DEBOUNCE_SECONDS) -> None:
        self._engine = engine
        self._debounce_seconds = debounce_seconds
        self._connections: dict[int, set[WebSocket]] = {}
        self._debounce_tasks: dict[int, asyncio.Task[None]] = {}

    async def connect(self, consultation_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(consultation_id, set()).add(websocket)

    def disconnect(self, consultation_id: int, websocket: WebSocket) -> None:
        self._connections.get(consultation_id, set()).discard(websocket)

    def notify_vote_cast(self, consultation_id: int) -> None:
        """Cancel any pending timer for this consultation and start a new
        one. Must be called from the event loop thread.
        """
        pending = self._debounce_tasks.get(consultation_id)
        if pending is not None and not pending.done():
            pending.cancel()
        self._debounce_tasks[consultation_id] = asyncio.create_task(
            self._debounced_refit(consultation_id)
        )

    async def _debounced_refit(self, consultation_id: int) -> None:
        try:
            await asyncio.sleep(self._debounce_seconds)
        except asyncio.CancelledError:
            return
        await self.refit_and_broadcast(consultation_id)

    async def refit_and_broadcast(self, consultation_id: int) -> None:
        message = await asyncio.to_thread(self._refit_and_build_message, consultation_id)
        await self._broadcast(consultation_id, message)

    def _refit_and_build_message(self, consultation_id: int) -> dict[str, object]:
        """Runs in a worker thread with its own session: a session is not
        safe to share with the request thread that scheduled this refit.
        """
        with Session(self._engine) as session:
            model_run = fit_and_persist(session, consultation_id, FactorisationParams())
            result = result_from_model_run(model_run)
            statements = {
                s.id: s
                for s in session.exec(
                    select(Statement).where(Statement.consultation_id == consultation_id)
                ).all()
                if s.id is not None
            }
            vote_rows = session.exec(
                select(Vote).where(col(Vote.statement_id).in_(result.statement_ids))
            ).all()
            votes = [(v.participant_id, v.statement_id, v.value) for v in vote_rows]
            bridging, majority = build_rankings(result, votes, statements)

        return {
            "type": "rankings",
            "model_run_id": model_run.id,
            "bridging": _serialise(bridging),
            "majority": _serialise(majority),
        }

    async def _broadcast(self, consultation_id: int, message: dict[str, object]) -> None:
        dead = []
        for websocket in list(self._connections.get(consultation_id, ())):
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(consultation_id, websocket)
