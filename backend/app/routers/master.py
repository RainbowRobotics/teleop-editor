from fastapi import APIRouter, HTTPException
from app.robot.master_arm import MASTER

router = APIRouter(prefix="/master", tags=["master"])


@router.get("/state")
def state():
    return MASTER.state()


@router.post("/connect")
def connect():
    if not MASTER.connect():
        raise HTTPException(500, "Master connect failed")
    return MASTER.state()


@router.post("/disconnect")
def disconnect():
    MASTER.disconnect()
    return MASTER.state()
