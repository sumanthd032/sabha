"""The WebSocket channel for a consultation's live session.

A client that joins receives a rankings message every time a debounced
refit completes, whether the vote that triggered it came from this
socket's own participant or anyone else in the same consultation.
"""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from sabha.db import engine
from sabha.services.live import LiveSessionManager

router = APIRouter(prefix="/api/consultations/{consultation_id}", tags=["live"])

_default_manager = LiveSessionManager(engine=engine)


def get_live_manager() -> LiveSessionManager:
    """The process-wide live session manager, overridden in tests."""
    return _default_manager


@router.websocket("/live")
async def live_session(
    websocket: WebSocket,
    consultation_id: int,
    live_manager: LiveSessionManager = Depends(get_live_manager),
) -> None:
    await live_manager.connect(consultation_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        live_manager.disconnect(consultation_id, websocket)
