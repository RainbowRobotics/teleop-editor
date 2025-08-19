# app/routers/motion.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse
from typing import Set
from app.state import State
from app.models import SetProjectMsg, SeekMsg, PrefetchMsg
from app.motion.types import DOF
from pydantic import BaseModel

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def send_json(self, ws: WebSocket, data):
        await ws.send_json(data)

    async def broadcast_json(self, data):
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


Mgr = ConnectionManager()


@router.websocket("/ws/motion")
async def motion_ws(ws: WebSocket):
    await Mgr.connect(ws)
    try:
        while True:
            raw = await ws.receive_json()
            t = raw.get("type")
            if t == "set_project":
                msg = SetProjectMsg(**raw)
                State.set_project(msg.project)

                # 1) 보낸 사람에게 ACK
                await Mgr.send_json(ws, {"type": "ack", "ok": True})

                # 2) (선택) 다른 모두에게 프로젝트 변경 알림
                await Mgr.broadcast_json({"type": "project_updated"})
                # 필요하면 version/summary도 같이 보냄

            elif t == "seek":
                msg = SeekMsg(**raw)
                q = State.eval_at(msg.t_ms)
                await Mgr.broadcast_json(
                    {"type": "pose", "t_ms": msg.t_ms, "q": q}
                )  # TODO: broadcast로 보내도 되는걸까

            elif t == "prefetch":
                msg = PrefetchMsg(**raw)
                t0 = int(msg.center_ms - msg.window_ms // 2)
                t1 = int(msg.center_ms + msg.window_ms // 2)
                poses = State.eval_range(t0, t1, msg.step_ms)
                await Mgr.send_json(
                    ws,
                    {
                        "type": "prefetch_result",
                        "t0_ms": t0,
                        "step_ms": msg.step_ms,
                        "count": len(poses),
                        "poses": poses,
                    },
                )
    except WebSocketDisconnect:
        pass
    finally:
        Mgr.disconnect(ws)


class ExportCsvRequest(BaseModel):
    t0_ms: int = 0
    t1_ms: int | None = None
    step_ms: float | None = None
    include_header: bool = True


@router.post("/motion/export_csv")
async def export_csv(req: ExportCsvRequest):
    # 프로젝트 유무 확인
    rt = State.get_rt_project()
    if rt is None:
        raise HTTPException(status_code=400, detail="No project set")

    # 구간/간격 결정
    t0 = max(0, int(req.t0_ms))
    t1 = int(req.t1_ms) if req.t1_ms is not None else State.project_duration_ms()
    if t1 < t0:
        raise HTTPException(status_code=400, detail="Invalid time range")
    step_ms = float(req.step_ms) if req.step_ms is not None else State.default_step_ms()
    step_ms = max(1.0, step_ms)

    # 샘플 (편집/블렌드/브릿지 모두 포함한 최종 trajectory)
    samples = State.eval_range(t0, t1, step_ms)

    def _iter_csv():
        if req.include_header:
            head = ["time"] + [f"q{i}" for i in range(DOF)]
            yield ",".join(head) + "\n"

        t = float(t0)
        for row in samples:
            vals = [f"{t/1000.}"] + [f"{v:.9f}" for v in row]
            yield ",".join(vals) + "\n"
            t += step_ms

    return StreamingResponse(
        _iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="trajectory.csv"'},
    )
