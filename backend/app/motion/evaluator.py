# app/motion/evaluator.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import bisect
import math

import numpy as np
from ruckig import Ruckig, InputParameter, Trajectory as RuckigTrajectory, Result

from .types import Project as RTProject, Clip as RTClip, Blend as RTBlend, DOF
from .bridge_cache import BridgeKey, BridgeCache, BridgeCacheItem


# ----------------- NumPy helpers -----------------
def _clamp_idx(i: int, lo: int, hi: int) -> int:
    """정수 인덱스를 NumPy clip으로 일관 처리."""
    return int(np.clip(i, lo, hi))


def _zeros_np() -> np.ndarray:
    return np.zeros((DOF,), dtype=np.float64)


# ----------------- Blend ramp (only for overlaps) -----------------
def _blend_curve(alpha: float, curve: str) -> float:
    """0..1 → 0..1. clip 겹침에서만 사용. gap(브릿지)에는 사용하지 않는다."""
    a = float(np.clip(alpha, 0.0, 1.0))
    if curve == "smoothstep":
        # 3a^2 - 2a^3
        return a * a * (3.0 - 2.0 * a)
    if curve == "easeInOut":
        # cosine ease-in-out
        return 0.5 * (1.0 - math.cos(math.pi * a))
    # linear
    return a


def _ramp_weight(
    local_ms: float, length_ms: float, in_ms: int, out_ms: int, curve: str
) -> float:
    """겹침일 때만 쓰는 램프. 공격(in) / 유지 / 감쇠(out) 형태."""
    if length_ms <= 1e-9:
        return 1.0
    w = 1.0

    if in_ms > 0 and local_ms < in_ms:
        a = local_ms / float(max(in_ms, 1))
        w *= _blend_curve(a, curve)

    if out_ms > 0 and local_ms > (length_ms - out_ms):
        tail = length_ms - local_ms
        a = tail / float(max(out_ms, 1))
        w *= _blend_curve(a, curve)

    return float(np.clip(w, 0.0, 1.0))


# ----------------- Velocity estimation -----------------
def _finite_diff_vel(frames_np: np.ndarray, idx: int, dt: float) -> np.ndarray:
    """
    frames_np: shape [F, DOF]
    중앙차분(가능 시), 경계는 전/후진차분. 반환 shape [DOF]
    """
    F = frames_np.shape[0]
    if F <= 1:
        return np.zeros((DOF,), dtype=np.float64)
    idx = _clamp_idx(idx, 0, F - 1)
    if 0 < idx < F - 1:
        return (frames_np[idx + 1] - frames_np[idx - 1]) / (2.0 * dt)
    elif idx == 0:
        return (frames_np[1] - frames_np[0]) / dt
    else:
        return (frames_np[idx] - frames_np[idx - 1]) / dt


# ----------------- Limits -----------------
@dataclass
class Limits:
    v_max: List[float]
    a_max: List[float]
    j_max: List[float]
    control_dt: float = 1 / 240.0  # Ruckig 내부 통합 주기

    def __post_init__(self):
        assert (
            len(self.v_max) == DOF and len(self.a_max) == DOF and len(self.j_max) == DOF
        ), "limits length must equal DOF"


# ----------------- Evaluator -----------------
class TrajectoryEvaluator:
    """
    정책 (옵션 B):
      * 겹치는 시간대: crossfade/additive → 램프 사용.
      * 빈 구간(gap): Ruckig 브릿지 (minimum_duration = gap_sec). 램프 미사용.
      * 브릿지 경계 상태(q, v)는 그 시점의 '블렌딩된 실제 상태'를 사용.
      * 클립 내부: NumPy 선형 보간.
    """

    def __init__(self, limits: Limits):
        self.lim = limits
        self._ruckig = Ruckig(DOF, limits.control_dt)
        self._cache = BridgeCache()

        # 런타임 상태
        self._proj: Optional[RTProject] = None
        self._clips_sorted: List[RTClip] = []
        self._t0s: np.ndarray = np.empty((0,), dtype=np.int64)  # 이웃 탐색용

        # 가속화 캐시
        self._src_frames_np: Dict[str, np.ndarray] = {}  # [F, DOF], float64
        self._src_dt: Dict[str, float] = {}
        self._src_dt_ms: Dict[str, float] = {}

    # ---------- project ----------
    def set_project(self, p: RTProject) -> None:
        self._proj = p
        self._clips_sorted = sorted(p.clips, key=lambda c: c.t0)
        self._t0s = np.fromiter(
            (c.t0 for c in self._clips_sorted),
            dtype=np.int64,
            count=len(self._clips_sorted),
        )
        self._cache.clear()

        # 소스 프레임 NumPy로 캐싱
        self._src_frames_np.clear()
        self._src_dt.clear()
        self._src_dt_ms.clear()
        for sid, s in p.sources.items():
            arr = np.asarray(s.frames, dtype=np.float64)  # [F, DOF]
            if arr.ndim != 2 or arr.shape[1] != DOF:
                raise ValueError(f"Source {sid} frames must be [F,{DOF}]")
            self._src_frames_np[sid] = arr
            self._src_dt[sid] = float(s.dt)
            self._src_dt_ms[sid] = float(s.dt) * 1000.0

    # ---------- public ----------
    def eval_at(self, t_ms: int) -> List[float]:
        if self._proj is None:
            return _zeros_np().tolist()

        # 1) 스택 구성
        normal_stack, additive_stack = self._gather_stacks(t_ms)

        # 2) 스택 합성 (겹침이면 블렌딩, 없으면 None)
        base = self._combine_stacks(normal_stack, additive_stack)

        if base is None:
            # 3) 커버가 전혀 없으면 → 브릿지 사용
            prev_c, next_c = self._find_neighbors(t_ms)
            if prev_c and next_c:
                qb = self._sample_bridge(prev_c, next_c, t_ms)
                if qb is not None:
                    return qb
            return _zeros_np().tolist()

        return base.tolist()

    def eval_range(self, t0_ms: int, t1_ms: int, step_ms: float) -> List[List[float]]:
        """t0..t1 (inclusive-ish) 구간을 step_ms 간격으로 샘플."""
        if t1_ms < t0_ms:
            return []
        out: List[List[float]] = []
        t = float(t0_ms)
        while t <= t1_ms + 1e-6:
            out.append(self.eval_at(int(round(t))))
            t += step_ms
        return out

    # ---------- internals : shared ----------
    def _gather_stacks(self, t_ms: int) -> Tuple[
        List[tuple[int, float, np.ndarray, RTClip]],
        List[tuple[float, np.ndarray, RTClip]],
    ]:
        """
        현재 시점 t_ms에서 유효한 클립들을 모아
        - normal_stack: (priority, weight, pose(np.ndarray), clip)
        - additive_stack: (weight, pose(np.ndarray), clip)
        로 나눈다.
        """
        normal_stack: List[tuple[int, float, np.ndarray, RTClip]] = []
        additive_stack: List[tuple[float, np.ndarray, RTClip]] = []

        for c in self._clips_sorted:
            q = self._sample_clip_at(c, t_ms)
            if q is None:
                continue

            frames = self._src_frames_np[c.sourceId]
            F = frames.shape[0]
            dt_ms = self._src_dt_ms[c.sourceId]
            inF = _clamp_idx(c.inFrame, 0, F - 1)
            outF = _clamp_idx(c.outFrame, 1, F)
            length_ms = 0.0 if outF <= inF + 1 else (outF - inF - 1) * dt_ms
            local_ms = float(t_ms - c.t0)

            b: RTBlend = c.blend
            mode = b.mode
            w = float(b.weight) * _ramp_weight(
                local_ms, length_ms, int(b.inMs), int(b.outMs), b.curve
            )
            if w <= 1e-12:
                continue

            if mode == "additive":
                additive_stack.append((w, q, c))
            elif mode == "crossfade":
                normal_stack.append((int(b.priority), w, q, c))
            else:  # "override"
                normal_stack.append((int(b.priority), 1.0, q, c))

        return normal_stack, additive_stack

    def _combine_stacks(
        self,
        normal_stack: List[tuple[int, float, np.ndarray, RTClip]],
        additive_stack: List[tuple[float, np.ndarray, RTClip]],
    ) -> Optional[np.ndarray]:
        """
        - normal_stack과 additive_stack을 합쳐 최종 pose(np.ndarray)를 만든다.
        - 둘 다 비어있으면 None (브릿지 후보)
        """
        covered = bool(normal_stack) or bool(additive_stack)
        if not covered:
            return None

        # base: override > crossfade(정규화)
        if normal_stack:
            overrides = [x for x in normal_stack if x[3].blend.mode == "override"]
            if overrides:
                overrides.sort(key=lambda x: -x[0])  # priority desc
                base = overrides[0][2]
            else:
                weights = np.array([x[1] for x in normal_stack], dtype=np.float64)
                wsum = float(weights.sum())
                if wsum <= 1e-12:
                    base = normal_stack[0][2]
                else:
                    weights /= wsum
                    qs = np.stack([x[2] for x in normal_stack], axis=0)  # [K, DOF]
                    base = (weights[:, None] * qs).sum(axis=0)
        else:
            base = _zeros_np()

        # additive 누적
        if additive_stack:
            add = np.add.reduce([w * q for (w, q, _) in additive_stack], axis=0)
            base = base + add

        return base

    # ---------- internals : sampling ----------
    def _sample_clip_at(self, c: RTClip, t_ms: int) -> Optional[np.ndarray]:
        frames = self._src_frames_np.get(c.sourceId)
        if frames is None:
            return None
        F = frames.shape[0]
        dt_ms = self._src_dt_ms[c.sourceId]

        inF = _clamp_idx(c.inFrame, 0, F - 1)
        outF = _clamp_idx(c.outFrame, 1, F)
        length_ms = (outF - inF) * dt_ms  # <=0이면 단일 프레임 취급
        local = t_ms - c.t0
        if local < 0 or local > length_ms:
            return None

        # 연속 인덱스 보간
        f_cont = inF + (local / dt_ms)
        f0 = int(np.floor(f_cont))
        frac = f_cont - f0

        f0 = _clamp_idx(f0, inF, outF - 1)
        f1 = _clamp_idx(f0 + 1, inF, outF - 1)

        q0 = frames[f0]
        q1 = frames[f1]
        if f1 == f0 or frac <= 1e-12:
            return q0.copy()
        return q0 * (1.0 - frac) + q1 * frac

    def _find_neighbors(self, t_ms: int) -> Tuple[Optional[RTClip], Optional[RTClip]]:
        # bisect로 O(log N)
        idx = bisect.bisect_left(self._t0s, t_ms)
        prev_c = (
            self._clips_sorted[idx - 1]
            if 0 <= idx - 1 < len(self._clips_sorted)
            else None
        )
        next_c = self._clips_sorted[idx] if 0 <= idx < len(self._clips_sorted) else None
        return prev_c, next_c

    # ----- blended-only sampler (for bridge boundaries) -----
    def _eval_blended_no_bridge(self, t_ms: int) -> Optional[np.ndarray]:
        """겹치는 클립들만 합성해서 pose 반환. (빈 구간이면 None)"""
        normal_stack, additive_stack = self._gather_stacks(t_ms)
        return self._combine_stacks(normal_stack, additive_stack)

    def _estimate_vel_blended(self, t_ms: int, h_ms: float) -> Optional[np.ndarray]:
        """블렌딩 평가로 q(t±h)를 구해 중앙차분. 둘 중 하나라도 None이면 None."""
        qm = self._eval_blended_no_bridge(int(round(t_ms - h_ms)))
        qp = self._eval_blended_no_bridge(int(round(t_ms + h_ms)))
        if qm is None or qp is None:
            return None
        h = max(h_ms, 1e-3) / 1000.0  # seconds
        return (qp - qm) / (2.0 * h)

    # ----- clip endpoint states (fallbacks) -----
    def _clip_end_state(
        self, c: RTClip
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int]:
        frames = self._src_frames_np[c.sourceId]
        F = frames.shape[0]
        dt = self._src_dt[c.sourceId]
        dt_ms = self._src_dt_ms[c.sourceId]

        inF = _clamp_idx(c.inFrame, 0, F - 1)
        outF = _clamp_idx(c.outFrame, 1, F)
        endF = inF if outF <= inF + 1 else (outF - 1)
        gap_start = c.t0 if outF <= inF + 1 else int(c.t0 + (outF - inF - 1) * dt_ms)

        q = frames[endF]
        v = _finite_diff_vel(frames, endF, dt)
        a = np.zeros((DOF,), dtype=np.float64)
        return q, v, a, gap_start

    def _clip_start_state(
        self, c: RTClip
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int]:
        frames = self._src_frames_np[c.sourceId]
        dt = self._src_dt[c.sourceId]
        inF = _clamp_idx(c.inFrame, 0, frames.shape[0] - 1)
        q = frames[inF]
        v = _finite_diff_vel(frames, inF, dt)
        a = np.zeros((DOF,), dtype=np.float64)
        return q, v, a, c.t0

    # ----- bridge (gap only) -----
    def _sample_bridge(
        self, prev_c: RTClip, next_c: RTClip, t_ms: int
    ) -> Optional[np.ndarray]:
        # 빈 구간에서만 호출됨
        # 1) gap 시간 계산
        _, _, _, gap_start = self._clip_end_state(prev_c)
        _, _, _, next_start = self._clip_start_state(next_c)
        if next_start <= gap_start:
            # 이상 상황: 겹침/역전 → 직전 포즈 유지
            q_end, _, _, _ = self._clip_end_state(prev_c)
            return q_end.copy()

        # Gap 길이(초) = minimum_duration에 그대로 사용
        T_gap = (next_start - gap_start) / 1000.0

        # 2) blended 경계 상태 계산 (겹침 영향 반영)
        prev_dt_ms = self._src_dt_ms[prev_c.sourceId]
        next_dt_ms = self._src_dt_ms[next_c.sourceId]
        h_ms = float(min(prev_dt_ms, next_dt_ms, 8.0))  # 수치 안정용

        # blended positions at t0-ε, t1+ε
        q0 = self._eval_blended_no_bridge(int(round(gap_start - h_ms)))
        q1 = self._eval_blended_no_bridge(int(round(next_start + h_ms)))

        # fallback: blended가 없으면 소스 기반 엔드/스타트 사용
        if q0 is None:
            q0, _, _, _ = self._clip_end_state(prev_c)
        if q1 is None:
            q1, _, _, _ = self._clip_start_state(next_c)

        # blended velocities at t0, t1 (중앙차분)
        v0 = self._estimate_vel_blended(gap_start, h_ms)
        v1 = self._estimate_vel_blended(next_start, h_ms)
        if v0 is None:
            frames_prev = self._src_frames_np[prev_c.sourceId]
            v0 = _finite_diff_vel(
                frames_prev,
                _clamp_idx(prev_c.outFrame - 1, 0, frames_prev.shape[0] - 1),
                self._src_dt[prev_c.sourceId],
            )
        if v1 is None:
            frames_next = self._src_frames_np[next_c.sourceId]
            v1 = _finite_diff_vel(
                frames_next,
                _clamp_idx(next_c.inFrame, 0, frames_next.shape[0] - 1),
                self._src_dt[next_c.sourceId],
            )

        a0 = np.zeros((DOF,), dtype=np.float64)
        a1 = np.zeros((DOF,), dtype=np.float64)

        # 3) 캐시 키 & 조회
        key = BridgeKey(
            prev_id=prev_c.id,
            next_id=next_c.id,
            prev_in=prev_c.inFrame,
            prev_out=prev_c.outFrame,
            next_in=next_c.inFrame,
            next_out=next_c.outFrame,
            prev_t0=prev_c.t0,
            next_t0=next_c.t0,
            dt_ms_prev=int(round(prev_dt_ms)),
            dt_ms_next=int(round(next_dt_ms)),
        )
        item = self._cache.get(key)

        if item is None or abs(item.T_ms - (T_gap * 1000.0)) > 0.5:
            traj = self._build_ruckig_bridge(q0, v0, a0, q1, v1, a1, T_gap)
            item = BridgeCacheItem(
                t0_ms=gap_start,
                T_ms=T_gap * 1000.0,
                duration_s=traj.duration,
                traj=traj,
            )
            self._cache.put(key, item)

        # 4) 샘플
        t_local = (t_ms - item.t0_ms) / 1000.0
        t_local = max(0.0, min(t_local, item.traj.duration))

        q, dq, ddq = item.traj.at_time(t_local)
        return q

    def _build_ruckig_bridge(
        self,
        q0: np.ndarray,
        v0: np.ndarray,
        a0: np.ndarray,
        q1: np.ndarray,
        v1: np.ndarray,
        a1: np.ndarray,
        T_gap: float,
    ) -> RuckigTrajectory:
        """Ruckig로 브릿지 생성. minimum_duration=T_gap 지정 (gap 전용)."""
        ip = InputParameter(DOF)

        ip.current_position = q0
        ip.current_velocity = v0
        ip.current_acceleration = a0

        ip.target_position = q1
        ip.target_velocity = v1
        ip.target_acceleration = a1

        ip.max_velocity = np.array(self.lim.v_max, dtype=np.float64)
        ip.max_acceleration = np.array(self.lim.a_max, dtype=np.float64)
        ip.max_jerk = np.array(self.lim.j_max, dtype=np.float64)

        # gap 시간 강제
        ip.minimum_duration = float(T_gap)

        traj = RuckigTrajectory(DOF)
        res = self._ruckig.calculate(ip, traj)
        if res not in (Result.Working, Result.Finished):
            # 실패 시 제한 완화(jerk ↑) 후 재시도
            ip.max_jerk *= 1.25
            res = self._ruckig.calculate(ip, traj)
            if res not in (Result.Working, Result.Finished):
                # 여전히 실패하면 빈 trajectory 반환 → 호출부에서 q0 유지
                return RuckigTrajectory(DOF)
        return traj
