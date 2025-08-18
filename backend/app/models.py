# app/models.py
from __future__ import annotations
from typing import Dict, List, Optional, Literal, Any
from pydantic import BaseModel, Field, model_validator

from app.motion.types import DOF


# ---------- Core API Schemas ----------
class Source(BaseModel):
    id: str
    dt: float = Field(..., gt=0, description="Seconds per frame (uniform sampling)")
    frames: List[List[float]] = Field(
        ..., description=f"List of frames; each pose must have length {DOF}"
    )
    name: Optional[str] = None

    @model_validator(mode="after")
    def _check_frames(self):
        if not self.frames:
            raise ValueError("Source.frames must not be empty")
        for i, q in enumerate(self.frames):
            if len(q) != DOF:
                raise ValueError(
                    f"Source.frames[{i}] must have length {DOF}, got {len(q)}"
                )
        return self


BlendMode = Literal["override", "crossfade", "additive"]
BlendCurve = Literal["linear", "smoothstep", "easeInOut"]


class Blend(BaseModel):
    mode: BlendMode = Field("override", description="override | crossfade | additive")
    inMs: int = Field(0, ge=0, description="Fade-in duration (ms)")
    outMs: int = Field(0, ge=0, description="Fade-out duration (ms)")
    curve: BlendCurve = Field("linear", description="Weight curve")
    weight: float = Field(1.0, ge=0.0, description="Blend weight")
    priority: int = Field(0, description="Priority (higher wins for override)")


class Clip(BaseModel):
    id: str
    sourceId: str
    t0: int = Field(..., ge=0, description="Start time (ms)")
    inFrame: int = Field(..., ge=0, description="Inclusive frame index")
    outFrame: int = Field(..., ge=1, description="Exclusive frame index")
    name: Optional[str] = None
    blend: Optional[Blend] = Field(default_factory=Blend)

    @model_validator(mode="after")
    def _check_range(self):
        if self.outFrame <= self.inFrame:
            raise ValueError("Clip.outFrame must be > inFrame")
        return self


class Project(BaseModel):
    lengthMs: int = Field(0, ge=0, description="Project length (ms)")
    sources: Dict[str, Source] = Field(
        default_factory=dict, description="Sources by ID"
    )
    clips: List[Clip] = Field(default_factory=list, description="Clip list")


# ---------- WS / API Payloads ----------
class SetProjectMsg(BaseModel):
    type: Literal["set_project"] = "set_project"
    project: Project


class ApplyOpsMsg(BaseModel):
    type: Literal["apply_ops"] = "apply_ops"
    ops: List[Dict[str, Any]]


class SeekMsg(BaseModel):
    type: Literal["seek"] = "seek"
    t_ms: int


class PrefetchMsg(BaseModel):
    type: Literal["prefetch"] = "prefetch"
    center_ms: int
    window_ms: int = 4000
    step_ms: float = 16.67


# ---------- Robot / Quest ----------
class RobotConnectReq(BaseModel):
    address: str = Field("localhost:50051", description="Robot gRPC address")


class QuestConnectReq(BaseModel):
    local_ip: str
    local_port: int = Field(5005, description="UDP listen port")
    quest_ip: str
    quest_port: int = Field(6000, description="Quest UDP port")


class SimpleOkResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
