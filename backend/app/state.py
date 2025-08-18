import json
import logging
import threading
from typing import Optional, List
from copy import deepcopy

from app.motion.evaluator import TrajectoryEvaluator, Limits
from app.motion.types import DOF, Project as RTProject
from app.motion.adapter import to_runtime, from_runtime
from app.models import Project as PydProject

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

        # Project state
        lim = Limits(v_max=DEFAULT_V_MAX, a_max=DEFAULT_A_MAX, j_max=DEFAULT_J_MAX)
        self._evaluator = TrajectoryEvaluator(limits=lim)
        self._rt_project: Optional[RTProject] = None

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
    def quest_state(self) -> Optional[dict]:
        """Get the quest state in a thread-safe manner."""
        with self._lock:
            return deepcopy(self._quest_state)

    @quest_state_json.setter
    def quest_state(self, value: dict):
        """Set the quest state and ensure it is thread-safe."""
        with self._lock:
            self._quest_state = value

    def set_project(self, project: PydProject):
        rt = to_runtime(project)
        with self._lock:
            self._rt_project = rt
            self._evaluator.set_project(rt)

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


State = RuntimeState()
