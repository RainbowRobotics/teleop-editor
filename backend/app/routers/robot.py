# backend/app/routers/robot.py
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from app.robot.robot import ROBOT

router = APIRouter(prefix="/robot", tags=["robot"])


class ConnectReq(BaseModel):
    address: str


class EnableReq(BaseModel):
    control_mode: str = "position"  # 'position' | 'impedance'


@router.get("/state")
def state():
    return ROBOT.state()  # 200 JSON


@router.post("/connect", status_code=status.HTTP_204_NO_CONTENT)
def connect(req: ConnectReq):
    if not ROBOT.connect(req.address):
        raise HTTPException(status_code=500, detail="Robot connect failed")
    return Response(status_code=204)


@router.post("/enable", status_code=status.HTTP_204_NO_CONTENT)
def enable(req: EnableReq):
    if not ROBOT.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    # internally powers rails + tool flange 12V + servo + CM + READY
    if not ROBOT.enable(control_mode=req.control_mode):
        raise HTTPException(
            status_code=500, detail="Enable failed (power/tool/servo/cm)"
        )
    return Response(status_code=204)


@router.post("/stop", status_code=status.HTTP_204_NO_CONTENT)
def stop():
    ROBOT.stop()
    return Response(status_code=204)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect():
    ROBOT.disconnect()
    return Response(status_code=204)
