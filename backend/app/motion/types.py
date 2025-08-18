# app/motion/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

DOF = 24
BlendMode = Literal["override", "crossfade", "additive"]
BlendCurve = Literal["linear", "smoothstep", "easeInOut"]


@dataclass(frozen=True)
class Source:
    id: str
    dt: float  # seconds per frame (uniform)
    frames: List[List[float]]  # shape [F][24]
    name: Optional[str] = None


@dataclass(frozen=True)
class Blend:
    mode: BlendMode = "override"
    inMs: int = 0
    outMs: int = 0
    curve: BlendCurve = "linear"
    weight: float = 1.0
    priority: int = 0


@dataclass(frozen=True)
class Clip:
    id: str
    sourceId: str
    t0: int  # ms
    inFrame: int  # inclusive
    outFrame: int  # exclusive
    name: Optional[str] = None
    blend: Blend = Blend()


@dataclass
class Project:
    lengthMs: int = 0
    sources: Dict[str, Source] = field(default_factory=dict)
    clips: List[Clip] = field(default_factory=list)
