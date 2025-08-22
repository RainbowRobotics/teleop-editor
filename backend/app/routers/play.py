# backend/app/routers/play.py
from fastapi import APIRouter, HTTPException, status, Response
from pydantic import BaseModel
from app.robot.robot import ROBOT

router = APIRouter(prefix="/play", tags=["play"])


class PlayStartReq(BaseModel):
    t0_ms: float = 0.0


class SeekReq(BaseModel):
    marker_ms: int


@router.post("/start", status_code=status.HTTP_204_NO_CONTENT)
def play_start(req: PlayStartReq):
    ok, reason = ROBOT.can_play()
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)
    if not ROBOT.start_play(t0_ms=float(req.t0_ms)):
        raise HTTPException(status_code=500, detail="Failed to start play")
    return Response(status_code=204)


@router.post("/stop", status_code=status.HTTP_204_NO_CONTENT)
def play_stop():
    ROBOT.stop_play()
    return Response(status_code=204)


@router.post("/seek", status_code=status.HTTP_204_NO_CONTENT)
def play_seek(req: SeekReq):
    if not ROBOT.seek(req.marker_ms):
        raise HTTPException(status_code=400, detail="Seek failed")
    return Response(status_code=204)


@router.get("/state")
def play_state():
    return ROBOT.play_state()  # 200 JSON
