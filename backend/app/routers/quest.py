from fastapi import APIRouter, HTTPException, Response, status
from app.config import settings
from app.models import QuestConnectReq
from app.services.quest_service import quest_service

router = APIRouter(prefix="", tags=["quest"])


@router.post("/quest/connect", status_code=status.HTTP_204_NO_CONTENT)
async def connect_quest(req: QuestConnectReq):
    quest_port = req.quest_port or settings.quest_default_port
    local_port = req.local_port or settings.local_default_port

    ok = quest_service.start_udp_listener(req.local_ip, local_port)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to start UDP listener")

    ok = quest_service.announce_to_quest(
        req.local_ip, local_port, req.quest_ip, quest_port
    )
    if not ok:
        # listener는 켜졌을 수 있으므로 필요시 정리
        quest_service.stop_udp_listener()
        raise HTTPException(status_code=500, detail="Failed to announce to Quest")

    return Response(status_code=204)


@router.post("/quest/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_quest():
    quest_service.stop_udp_listener()
    return Response(status_code=204)
