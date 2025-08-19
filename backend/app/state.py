import json
import logging
import threading
from typing import Optional, List
from scipy.spatial.transform import Rotation as R
from copy import deepcopy
import numpy as np

from app.motion.evaluator import TrajectoryEvaluator, Limits
from app.motion.types import DOF, Project as RTProject
from app.motion.adapter import to_runtime, from_runtime
from app.models import Project as PydProject
from app.robot.robot import ROBOT

DEFAULT_V_MAX = [10.0] * DOF
DEFAULT_A_MAX = [50.0] * DOF
DEFAULT_J_MAX = [1000.0] * DOF


class RuntimeState:
    """Singleton class to manage the runtime state of the application."""

    def __init__(self):
        self._lock = threading.Lock()
        self._quest_state: Optional[dict] = None
        self.robot_connected: bool = False
        self.quest_udp_running: bool = False
        self.quest_udp_bind: Optional[tuple[str, int]] = None
        self.quest_seq: int = 0

        # Quest 헤드 마운트
        self._quest_head_position: np.ndarray = None
        self._quest_head_quat: np.ndarray = None

        # Project state
        lim = Limits(v_max=DEFAULT_V_MAX, a_max=DEFAULT_A_MAX, j_max=DEFAULT_J_MAX)
        self._evaluator = TrajectoryEvaluator(limits=lim)
        self._rt_project: Optional[RTProject] = None

        ROBOT.set_play_evaluator(self._evaluator.eval_range, self._evaluator.eval_at)

    @property
    def quest_state_json(self) -> str:
        """Return the quest state as a JSON string."""
        with self._lock:
            return (
                json.dumps(self._quest_state, separators=(",", ":"))
                if self._quest_state
                else "{}"
            )

    @property
    def quest_head_position(self) -> Optional[np.ndarray]:
        """Get the quest head position in a thread-safe manner."""
        with self._lock:
            return self._quest_head_position.copy()

    @property
    def quest_head_quat(self) -> Optional[np.ndarray]:
        """Get the quest head position in a thread-safe manner."""
        with self._lock:
            return self._quest_head_quat.copy()

    @property
    def quest_state(self) -> Optional[dict]:
        """Get the quest state in a thread-safe manner."""
        with self._lock:
            return deepcopy(self._quest_state)

    @quest_state_json.setter
    def quest_state(self, value: dict):
        """Set the quest state and ensure it is thread-safe."""
        with self._lock:
            self._quest_state = value

            head_controller = self._quest_state["head"]
            self._quest_head_position = np.asarray(head_controller["position"], dtype=np.float64)
            self._quest_head_quat = np.asarray(head_controller["rotation"], dtype=np.float64)

    def set_project(self, project: PydProject):
        rt = to_runtime(project)
        with self._lock:
            self._rt_project = rt
            self._evaluator.set_project(rt)

    def get_rt_project(self) -> Optional[RTProject]:
        with self._lock:
            return deepcopy(self._rt_project) if self._rt_project is not None else None

    def eval_at(self, t_ms: int) -> List[float]:
        with self._lock:
            if not self._rt_project:
                return [0.0] * DOF
            return self._evaluator.eval_at(t_ms)

    def eval_range(self, t0_ms: int, t1_ms: int, step_ms: float) -> List[List[float]]:
        with self._lock:
            if not self._rt_project:
                return [[0.0] * DOF]
            return self._evaluator.eval_range(t0_ms, t1_ms, step_ms)

    def project_duration_ms(self) -> int:
        with self._lock:
            p = self._rt_project
            if p is None:
                return 0
            max_end = 0
            for c in p.clips:
                s = p.sources.get(c.sourceId)
                if not s:
                    continue
                frames = max(1, c.outFrame - c.inFrame)
                dur = frames * s.dt * 1000.0
                end = max(0, c.t0) + dur
                if end > max_end:
                    max_end = end
            return int(round(max_end))

    def default_step_ms(self) -> float:
        with self._lock:
            p = self._rt_project
            if p is None or not p.sources:
                return 33.0  # 30Hz fallback
            ms = [s.dt * 1000.0 for s in p.sources.values()]
            return float(max(1.0, min(ms)))

    # Internal
    @staticmethod
    def _pose_to_se3(position, rotation_quat):
        T = np.eye(4)
        T[:3, :3] = R.from_quat(rotation_quat).as_matrix()
        T[:3, 3] = position
        return T


State = RuntimeState()
