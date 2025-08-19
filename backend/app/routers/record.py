# backend/app/routers/record.py
from fastapi import APIRouter, Response, HTTPException, status
from app.robot.robot import ROBOT


router = APIRouter(prefix="/record", tags=["record"])


@router.post("/start")
def record_start():
    # Fail if robot not connected
    if not ROBOT.connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Robot not connected",
        )
    # Fail if already active
    st = ROBOT.recording_state()
    if st.get("active"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Recording already active"
        )
    ok = ROBOT.start_recording()
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start recording",
        )
    return {"ok": True}


@router.post("/stop")
def record_stop():
    st = ROBOT.recording_state()
    if not st.get("active"):
        # Idempotent stop: still OK, return current counters
        info = ROBOT.stop_recording()
        return {"ok": True, **info}
    info = ROBOT.stop_recording()
    return {"ok": True, **info}


@router.get("/state")
def record_state():
    return ROBOT.recording_state()


@router.get("/download")
def record_download():
    fname, data = ROBOT.build_recording_csv()
    headers = {
        "Content-Disposition": f'attachment; filename="{fname}"',
        "Content-Type": "text/csv; charset=utf-8",
    }
    return Response(content=data, headers=headers, media_type="text/csv")


@router.get("/summary")
def record_summary():
    return ROBOT.build_recording_summary()
