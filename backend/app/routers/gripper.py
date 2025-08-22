from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from app.robot.gripper import GRIPPER

router = APIRouter(prefix="/gripper", tags=["gripper"])


class NVec(BaseModel):
    n: list[float]


@router.get("/state")
def state():
    return GRIPPER.state()  # 200 JSON


@router.post("/connect", status_code=status.HTTP_204_NO_CONTENT)
def connect():
    if not GRIPPER.connect(verbose=True):
        raise HTTPException(status_code=500, detail="Gripper connect failed")
    return Response(status_code=204)


@router.post("/homing", status_code=status.HTTP_204_NO_CONTENT)
def homing():
    if not GRIPPER.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    if not GRIPPER.homing():
        raise HTTPException(status_code=500, detail="Homing failed")
    return Response(status_code=204)


@router.post("/start", status_code=status.HTTP_204_NO_CONTENT)
def start():
    if not GRIPPER.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    GRIPPER.start()
    return Response(status_code=204)


@router.post("/stop", status_code=status.HTTP_204_NO_CONTENT)
def stop():
    GRIPPER.stop()
    return Response(status_code=204)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect():
    GRIPPER.disconnect()
    return Response(status_code=204)


@router.post("/target/n", status_code=status.HTTP_204_NO_CONTENT)
def set_n(body: NVec):
    if not (GRIPPER.connected and GRIPPER.homed):
        raise HTTPException(status_code=400, detail="Connect & home first")
    GRIPPER.set_target_normalized_vec(body.n)
    return Response(status_code=204)
