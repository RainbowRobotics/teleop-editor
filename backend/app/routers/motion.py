# app/routers/motion.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
from app.state import State
from app.models import SetProjectMsg, SeekMsg, PrefetchMsg

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
                await Mgr.broadcast_json({"type": "pose", "t_ms": msg.t_ms, "q": q}) # TODO: broadcast로 보내도 되는걸까

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
