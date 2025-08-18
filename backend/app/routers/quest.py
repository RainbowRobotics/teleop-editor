from fastapi import APIRouter
from app.config import settings
from app.models import QuestConnectReq, SimpleOkResponse
from app.services.quest_service import quest_service

router = APIRouter(prefix="", tags=["quest"])


@router.post("/quest/connect", response_model=SimpleOkResponse)
async def connect_quest(req: QuestConnectReq) -> SimpleOkResponse:
    """
    Connect to the quest at the specified address.

    :param req: Request containing the quest address.
    :return: Response indicating success or failure of the connection.
    """
    quest_port = req.quest_port or settings.quest_default_port
    local_port = req.local_port or settings.local_default_port

    ok = quest_service.start_udp_listener(req.local_ip, local_port)
    if not ok:
        return SimpleOkResponse(ok=False, error="Failed to start UDP listener")

    ok = quest_service.announce_to_quest(
        req.local_ip, local_port, req.quest_ip, quest_port
    )
    if not ok:
        return SimpleOkResponse(ok=False, error="Failed to announce to Quest")

    return SimpleOkResponse(ok=True, error=None)

@router.post("/quest/disconnect", response_model=SimpleOkResponse)
async def disconnect_quest() -> SimpleOkResponse:
    """
    Disconnect from the quest.

    :return: Response indicating success or failure of the disconnection.
    """
    quest_service.stop_udp_listener()
    return SimpleOkResponse(ok=True, error=None)