from fastapi import APIRouter, HTTPException, Response, status
from app.robot.master_arm import MASTER

router = APIRouter(prefix="/master", tags=["master"])


@router.get("/state")
def state():
    return MASTER.state()  # 200 JSON


@router.post("/connect", status_code=status.HTTP_204_NO_CONTENT)
def connect():
    if not MASTER.connect():
        raise HTTPException(status_code=500, detail="Master connect failed")
    return Response(status_code=204)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect():
    MASTER.disconnect()
    return Response(status_code=204)
