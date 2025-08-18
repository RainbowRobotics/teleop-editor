# backend/app/routers/robot.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.robot.robot import ROBOT

router = APIRouter(prefix="/robot", tags=["robot"])

class ConnectReq(BaseModel):
    address: str

class EnableReq(BaseModel):
    control_mode: str = "position"  # 'position' | 'impedance'

@router.get("/state")
def state(): return ROBOT.state()

@router.post("/connect")
def connect(req: ConnectReq):
    if not ROBOT.connect(req.address):
        raise HTTPException(500, "Robot connect failed")
    return ROBOT.state()

@router.post("/enable")
def enable(req: EnableReq):
    if not ROBOT.connected: raise HTTPException(400, "Not connected")
    # internally powers rails + tool flange 12V + servo + CM + READY
    if not ROBOT.enable(control_mode=req.control_mode):
        raise HTTPException(500, "Enable failed (power/tool/servo/cm)")
    return ROBOT.state()

@router.post("/stop")
def stop(): ROBOT.stop(); return ROBOT.state()

@router.post("/disconnect")
def disconnect(): ROBOT.disconnect(); return ROBOT.state()
