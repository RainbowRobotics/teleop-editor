from fastapi import APIRouter, Response, HTTPException, status
from app.robot.robot import ROBOT

router = APIRouter(prefix="/record", tags=["record"])


@router.post("/start", status_code=status.HTTP_204_NO_CONTENT)
def record_start():
    if not ROBOT.connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Robot not connected",
        )
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
    return Response(status_code=204)


@router.post("/stop", status_code=status.HTTP_204_NO_CONTENT)
def record_stop():
    # stop은 idempotent하게 동작하되, 본문은 비우고 204
    ROBOT.stop_recording()
    return Response(status_code=204)


@router.get("/state")
def record_state():
    return ROBOT.recording_state()  # 200 JSON


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
    return ROBOT.build_recording_summary()  # 200 JSON
