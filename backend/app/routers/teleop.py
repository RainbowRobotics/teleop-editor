from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from app.teleop.teleop import TELEOP
from app.robot.robot import ROBOT
from app.robot.master_arm import MASTER

router = APIRouter(prefix="/teleop", tags=["teleop"])


class StartReq(BaseModel):
    mode: str = "position"  # 'position' | 'impedance'


@router.get("/state")
def state():
    return TELEOP.state()  # 200 JSON


@router.post("/start", status_code=status.HTTP_204_NO_CONTENT)
def start(req: StartReq):
    if not (ROBOT.connected and ROBOT.ready):
        raise HTTPException(status_code=400, detail="Robot not ready")
    if not MASTER.connected:
        raise HTTPException(status_code=400, detail="Master not connected")
    TELEOP.start(control_mode=req.mode)
    return Response(status_code=204)


@router.post("/stop", status_code=status.HTTP_204_NO_CONTENT)
def stop():
    TELEOP.stop()
    return Response(status_code=204)
