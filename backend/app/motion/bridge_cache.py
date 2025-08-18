# app/motion/bridge_cache.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class BridgeKey:
    # 두 클립과 그 경계가 바뀌면 키가 달라지도록 구성
    prev_id: str
    next_id: str
    prev_in: int
    prev_out: int
    next_in: int
    next_out: int
    prev_t0: int
    next_t0: int
    dt_ms_prev: int
    dt_ms_next: int


@dataclass
class BridgeCacheItem:
    t0_ms: int  # gap 시작 (project time)
    T_ms: float  # gap 길이 (ms)
    duration_s: float  # ruckig trajectory duration (s)
    # ruckig Trajectory 객체를 런타임에 보관 (직렬화 X)
    traj: object  # ruckig.Trajectory


class BridgeCache:
    def __init__(self) -> None:
        self._map: Dict[BridgeKey, BridgeCacheItem] = {}

    def get(self, key: BridgeKey) -> Optional[BridgeCacheItem]:
        return self._map.get(key)

    def put(self, key: BridgeKey, item: BridgeCacheItem) -> None:
        self._map[key] = item

    def clear(self) -> None:
        self._map.clear()
