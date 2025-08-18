from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.teleop.teleop import TELEOP
from app.robot.robot import ROBOT
from app.robot.master_arm import MASTER

router = APIRouter(prefix="/teleop", tags=["teleop"])


class StartReq(BaseModel):
    mode: str = "position"  # 'position' | 'impedance'


@router.get("/state")
def state():
    return TELEOP.state()


@router.post("/start")
def start(req: StartReq):
    if not (ROBOT.connected and ROBOT.ready):
        raise HTTPException(400, "Robot not ready")
    if not MASTER.connected:
        raise HTTPException(400, "Master not connected")
    TELEOP.start(control_mode=req.mode)
    return TELEOP.state()


@router.post("/stop")
def stop():
    TELEOP.stop()
    return TELEOP.state()
