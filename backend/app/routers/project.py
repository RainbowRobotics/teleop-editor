# app/routers/project.py  (선택사항)
from fastapi import APIRouter
from app.models import Project as APIProject, SimpleOkResponse
from app.state import State

router = APIRouter()

_current: APIProject | None = None


@router.post("/api/project", response_model=SimpleOkResponse)
async def save_project(p: APIProject):
    global _current
    _current = p
    State.set_project(p)
    return SimpleOkResponse(ok=True)


@router.get("/api/project", response_model=APIProject)
async def load_project():
    return _current or APIProject()
