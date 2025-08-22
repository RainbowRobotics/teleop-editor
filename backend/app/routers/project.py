# app/routers/project.py
from fastapi import APIRouter, Response, status
from app.models import Project as APIProject
from app.state import State

router = APIRouter()

_current: APIProject | None = None


@router.post("/api/project", status_code=status.HTTP_204_NO_CONTENT)
async def save_project(p: APIProject):
    global _current
    _current = p
    State.set_project(p)
    return Response(status_code=204)


@router.get("/api/project", response_model=APIProject)
async def load_project():
    return _current or APIProject()
