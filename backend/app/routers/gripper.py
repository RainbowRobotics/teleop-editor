from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.robot.gripper import GRIPPER

router = APIRouter(prefix="/gripper", tags=["gripper"])


class NVec(BaseModel):
    n: list[float]


@router.get("/state")
def state():
    return GRIPPER.state()


@router.post("/connect")
def connect():
    if not GRIPPER.connect(verbose=True):
        raise HTTPException(500, "Gripper connect failed")
    return GRIPPER.state()


@router.post("/homing")
def homing():
    if not GRIPPER.connected:
        raise HTTPException(400, "Not connected")
    if not GRIPPER.homing():
        raise HTTPException(500, "Homing failed")
    return GRIPPER.state()


@router.post("/start")
def start():
    if not GRIPPER.connected:
        raise HTTPException(400, "Not connected")
    GRIPPER.start()
    return GRIPPER.state()


@router.post("/stop")
def stop():
    GRIPPER.stop()
    return GRIPPER.state()


@router.post("/disconnect")
def disconnect():
    GRIPPER.disconnect()
    return GRIPPER.state()


@router.post("/target/n")
def set_n(body: NVec):
    if not (GRIPPER.connected and GRIPPER.homed):
        raise HTTPException(400, "Connect & home first")
    GRIPPER.set_target_normalized_vec(body.n)
    return GRIPPER.state()
