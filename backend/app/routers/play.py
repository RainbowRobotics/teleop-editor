# backend/app/routers/play.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.robot.robot import ROBOT


router = APIRouter(prefix="/play", tags=["play"])


class PlayStartReq(BaseModel):
    t0_ms: float = 0.0


class SeekReq(BaseModel):
    marker_ms: int


@router.post("/start")
def play_start(req: PlayStartReq):
    ok, reason = ROBOT.can_play()
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)
    if not ROBOT.start_play(t0_ms=float(req.t0_ms)):
        raise HTTPException(status_code=500, detail="Failed to start play")
    return {"ok": True}


@router.post("/stop")
def play_stop():
    ROBOT.stop_play()
    return {"ok": True}


@router.post("/seek")
def play_seek(req: SeekReq):
    if not ROBOT.seek(req.marker_ms):
        raise HTTPException(status_code=400, detail="seek failed")
    return ROBOT.play_state()


@router.get("/state")
def play_state():
    return ROBOT.play_state()
