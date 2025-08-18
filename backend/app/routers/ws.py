import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.config import settings
from app.state import State

router = APIRouter(prefix="", tags=["ws"])


@router.websocket("/ws/quest")
async def quest_websocket(
    websocket: WebSocket,
    hz: int = Query(
        settings.quest_ws_default_hz,
        ge=settings.quest_ws_min_hz,
        le=settings.quest_ws_max_hz,
        description="WebSocket frequency in Hz",
    ),
):
    """
    WebSocket endpoint for Quest communication.

    :param websocket: The WebSocket connection.
    :param hz: Frequency of the WebSocket in Hz.
    """
    await websocket.accept()
    period = 1 / hz
    try:
        while True:
            frame = State.quest_state_json
            if frame is not None:
                await websocket.send_text(frame)
            await asyncio.sleep(period)
    except WebSocketDisconnect:
        logging.info("WebSocket connection closed")
    except Exception as e:
        logging.error(f"Error in WebSocket connection: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
