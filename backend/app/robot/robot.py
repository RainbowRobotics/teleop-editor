# backend/app/robot/robot.py
import time
import threading
from typing import Optional, Dict, Any, Union, Tuple, Callable, List

import numpy as np
import rby1_sdk as rby

from .common import Settings, READY_POSE


class RobotManager:
    """
    Robot connect/power/servo/control-manager, recording, and playback manager.
    """

    BASE_LINK_IDX = 0
    TORSO_5_LINK_IDX = 1

    # Timeline evaluators
    # eval_range(t0_ms, t1_ms, step_ms) -> List[np.ndarray] (full q for each sample)
    EvalRangeFn = Callable[[float, float, float], List[np.ndarray]]
    # eval_at is optional (not used in start, but available if you want in loop)
    EvalAtFn = Callable[[float], np.ndarray]

    def __init__(self) -> None:
        # Connection & model
        self.address: Optional[str] = None
        self.robot: Optional[rby.Robot_A] = None
        self.model = None
        self.stream = None

        # Dynamics
        self.dyn_model = None
        self.dyn_state = None
        self.robot_q: Optional[np.ndarray] = None
        self.robot_min_q = None
        self.robot_max_q = None
        self.robot_max_qdot = None
        self.robot_max_qddot = None

        # Cached kinematics bits
        self._lock = threading.Lock()
        self.update_time: Optional[float] = None
        self.torso_pose = None
        self.right_arm_q: Optional[np.ndarray] = None
        self.left_arm_q: Optional[np.ndarray] = None

        # Power / status
        self.connected = False
        self.ready = False
        self.power_detail: Dict[str, bool] = {}
        self.power_all_on = False
        self.tool_flange_12v: Dict[str, bool] = {}

        # DEBUG
        self.is_simulation = False

        # ---- Recording ----
        self._rec_lock = threading.Lock()
        self._rec_active = False
        self._rec_samples: list[list[float]] = []  # [time(s), *q]
        self._rec_joint_names: Optional[list[str]] = None
        self._rec_max_samples = 2_000_000

        # ---- Teleop & Play ----
        self.teleop_active = False  # flip this in your teleop start/stop
        self.playing = False
        self._play_lock = threading.Lock()
        self._play_stop = threading.Event()
        self._play_thread: Optional[threading.Thread] = None
        self._play_marker_ms: float = 0.0

        # Injected timeline evaluators
        self._eval_range: Optional[RobotManager.EvalRangeFn] = None
        self._eval_at: Optional[RobotManager.EvalAtFn] = None  # optional

    # -------------------------
    # Connection / state update
    # -------------------------
    def connect(self, address: str) -> bool:
        self.address = address
        self.robot = rby.create_robot(address, "a")  # MODEL FIXED
        if not self.robot.connect():
            self.connected = False
            return False

        self.model = self.robot.model()  # will report model_name='A'
        self.dyn_model = self.robot.get_dynamics()
        self.dyn_state = self.dyn_model.make_state(
            ["base", "link_torso_5"], self.model.robot_joint_names
        )
        self.robot_max_q = self.dyn_model.get_limit_q_upper(self.dyn_state)
        self.robot_min_q = self.dyn_model.get_limit_q_lower(self.dyn_state)
        self.robot_max_qdot = self.dyn_model.get_limit_qdot_upper(self.dyn_state)
        self.robot_max_qddot = self.dyn_model.get_limit_qddot_upper(self.dyn_state)
        self.connected = True
        if not self.is_simulation:
            self.power_detail = {"5v": False, "12v": False, "24v": False, "48v": False}
        else:
            self.power_detail = {"main": False}
        self.power_all_on = False
        self.tool_flange_12v = {"right": False, "left": False}

        PowerOn = rby.PowerState.State.PowerOn

        def state_cb(state: rby.RobotState_A):
            self.robot_q = state.target_position

            # kinematics cache
            self.dyn_state.set_q(self.robot_q)
            self.dyn_model.compute_forward_kinematics(self.dyn_state)
            with self._lock:
                self.update_time = time.time()
                self.torso_pose = self.dyn_model.compute_transformation(
                    self.dyn_state, self.BASE_LINK_IDX, self.TORSO_5_LINK_IDX
                )
                self.right_arm_q = self.robot_q[self.model.right_arm_idx]
                self.left_arm_q = self.robot_q[self.model.left_arm_idx]

            # recording tap
            try:
                if self.robot_q is not None:
                    with self._rec_lock:
                        if (
                            self._rec_active
                            and len(self._rec_samples) < self._rec_max_samples
                        ):
                            # Use loop period for time axis (seconds)
                            t = Settings.master_arm_loop_period * len(self._rec_samples)
                            self._rec_samples.append(
                                [float(t), *map(float, self.robot_q)]
                            )
            except Exception:
                pass

            # power rails
            try:
                detail: Dict[str, bool] = {}
                for i, key in enumerate(
                    ["5v", "12v", "24v", "48v"] if not self.is_simulation else ["main"]
                ):
                    detail[key] = state.power_states[i].state == PowerOn
                self.power_detail = detail
                self.power_all_on = all(detail.values()) if detail else False
            except Exception:
                try:
                    self.power_all_on = all(
                        ps.state == PowerOn for ps in state.power_states
                    )
                except Exception:
                    self.power_all_on = False

        self.robot.start_state_update(state_cb, 1 / Settings.master_arm_loop_period)
        return True

    def ensure_power_and_tools(self, timeout_s: float = 5.0) -> bool:
        if not self.connected:
            return False

        # power on rails
        if not self.power_all_on:
            if not self.robot.power_on(".*"):  # turns on 5/12/24/48
                return False

        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.power_all_on:
                break
            time.sleep(0.05)

        if not self.power_all_on:
            return False

        time.sleep(0.2)

        # tool flange 12V both sides
        if not self.is_simulation:
            ok_right = self.robot.set_tool_flange_output_voltage("right", 12)
            ok_left = self.robot.set_tool_flange_output_voltage("left", 12)
        else:
            ok_right = True
            ok_left = True
        self.tool_flange_12v["right"] = bool(ok_right)
        self.tool_flange_12v["left"] = bool(ok_left)
        return bool(ok_left and ok_right)

    def enable(
        self,
        servo_regex: str = "torso_.*|right_arm_.*|left_arm_.*",
        control_mode: str = "position",
    ) -> bool:
        if not self.connected:
            return False

        if not self.ensure_power_and_tools():
            return False

        if not self.robot.is_servo_on(servo_regex):
            if not self.robot.servo_on(servo_regex):
                return False

        self.robot.reset_fault_control_manager()
        if not self.robot.enable_control_manager():
            return False

        # optional tweak for impedance wrist speed
        if control_mode == "impedance":
            self.robot_max_qdot[self.model.right_arm_idx[-1]] *= 10
            self.robot_max_qdot[self.model.left_arm_idx[-1]] *= 10

        # go READY pose
        ok = self.move_ready(position_mode=(control_mode == "position"))
        self.ready = bool(
            ok and self.power_all_on and all(self.tool_flange_12v.values())
        )
        return self.ready

    def create_stream(self) -> bool:
        if self.stream is None or self.stream.is_done():
            self.stream = self.robot.create_command_stream(priority=1)
            return True
        return False

    # -------------------------
    # Commands / helpers
    # -------------------------
    def build_ready_command(
        self, position_mode: bool, control_hold_time: float = 0
    ) -> rby.RobotCommandBuilder:
        pose = READY_POSE["A"]
        right_builder = (
            rby.JointPositionCommandBuilder()
            if position_mode
            else rby.JointImpedanceControlCommandBuilder()
        )
        (
            right_builder.set_command_header(
                rby.CommandHeaderBuilder().set_control_hold_time(control_hold_time)
            )
            .set_position(pose.right_arm)
            .set_minimum_time(5)
        )
        if not position_mode:
            (
                right_builder.set_stiffness(
                    [Settings.impedance_stiffness] * len(pose.right_arm)
                )
                .set_damping_ratio(Settings.impedance_damping_ratio)
                .set_torque_limit(
                    [Settings.impedance_torque_limit] * len(pose.right_arm)
                )
            )

        left_builder = (
            rby.JointPositionCommandBuilder()
            if position_mode
            else rby.JointImpedanceControlCommandBuilder()
        )
        (
            left_builder.set_command_header(
                rby.CommandHeaderBuilder().set_control_hold_time(control_hold_time)
            )
            .set_position(pose.left_arm)
            .set_minimum_time(5)
        )
        if not position_mode:
            (
                left_builder.set_stiffness(
                    [Settings.impedance_stiffness] * len(pose.left_arm)
                )
                .set_damping_ratio(Settings.impedance_damping_ratio)
                .set_torque_limit(
                    [Settings.impedance_torque_limit] * len(pose.left_arm)
                )
            )

        torso_builder = (
            rby.JointPositionCommandBuilder()
            .set_command_header(
                rby.CommandHeaderBuilder().set_control_hold_time(control_hold_time)
            )
            .set_position(pose.torso)  # fixed typo
            .set_minimum_time(5)
        )

        return rby.RobotCommandBuilder().set_command(
            rby.ComponentBasedCommandBuilder().set_body_command(
                rby.BodyComponentBasedCommandBuilder()
                .set_torso_command(torso_builder)
                .set_right_arm_command(right_builder)
                .set_left_arm_command(left_builder)
            )
        )

    def _build_position_command_from_q(
        self, q: np.ndarray, min_time_s: float = 0.02
    ) -> rby.RobotCommandBuilder:
        """
        Create a full-body JointPosition command from a full q (model.robot_joint_names order).
        """
        if q is None or self.model is None:
            raise RuntimeError("Model or q is not available")

        torso_q = q[self.model.torso_idx]
        right_q = q[self.model.right_arm_idx]
        left_q = q[self.model.left_arm_idx]

        torso_builder = rby.JointPositionCommandBuilder().set_command_header(
            rby.CommandHeaderBuilder().set_control_hold_time(0)
        )
        if torso_q is not None:
            torso_builder.set_position(torso_q).set_minimum_time(min_time_s)

        right_builder = (
            rby.JointPositionCommandBuilder()
            .set_command_header(rby.CommandHeaderBuilder().set_control_hold_time(0))
            .set_position(right_q)
            .set_minimum_time(min_time_s)
        )

        left_builder = (
            rby.JointPositionCommandBuilder()
            .set_command_header(rby.CommandHeaderBuilder().set_control_hold_time(0))
            .set_position(left_q)
            .set_minimum_time(min_time_s)
        )

        return rby.RobotCommandBuilder().set_command(
            rby.ComponentBasedCommandBuilder().set_body_command(
                rby.BodyComponentBasedCommandBuilder()
                .set_torso_command(torso_builder)
                .set_right_arm_command(right_builder)
                .set_left_arm_command(left_builder)
            )
        )

    def get_current_pose(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if not self.connected:
            raise RuntimeError("아직 로봇 연결이 안되어있습니다.")

        current_time = time.time()
        with self._lock:
            if current_time - (self.update_time or 0) >= 1.0:
                state = self.robot.get_state()
                self.dyn_state.set_q(state.target_position)
                self.dyn_model.compute_forward_kinematics(self.dyn_state)

                self.update_time = current_time
                self.torso_pose = self.dyn_model.compute_transformation(
                    self.dyn_state, self.BASE_LINK_IDX, self.TORSO_5_LINK_IDX
                )
                self.right_arm_q = self.robot_q[self.model.right_arm_idx]
                self.left_arm_q = self.robot_q[self.model.left_arm_idx]

        return (self.torso_pose, self.right_arm_q, self.left_arm_q)

    def move_ready(self, position_mode: bool) -> bool:
        fb = self.robot.send_command(self.build_ready_command(position_mode)).get()
        return fb.finish_code == rby.RobotCommandFeedback.FinishCode.Ok

    def stop(self):
        if not self.connected:
            return
        try:
            self.robot.cancel_control()
        except Exception:
            pass
        time.sleep(0.2)

    def disconnect(self):
        if not self.connected:
            return
        try:
            self.robot.stop_state_update()
        except Exception:
            pass
        try:
            self.robot.disable_control_manager()
        except Exception:
            pass
        try:
            self.robot.power_off("12v" if not self.is_simulation else "")
        except Exception:
            pass
        self.connected = False
        self.ready = False
        self.power_all_on = False
        self.tool_flange_12v = {"right": False, "left": False}

    # -------------------------
    # Public state snapshot
    # -------------------------
    def state(self) -> Dict[str, Any]:
        try:
            torso_pose, right_arm_q, left_arm_q = self.get_current_pose()
        except Exception:
            torso_pose, right_arm_q, left_arm_q = None, None, None

        return {
            "model": "A",
            "address": self.address,
            "connected": self.connected,
            "ready": self.ready,
            "has_stream": self.stream is not None,
            "power_all_on": self.power_all_on,
            "power_detail": self.power_detail,
            "tool_flange_12v": self.tool_flange_12v,
            "playing": self.playing,
            "teleop_active": self.teleop_active,
            "state": {
                "torso_pose": torso_pose.tolist() if torso_pose is not None else None,
                "right_arm_q": (
                    right_arm_q.tolist() if right_arm_q is not None else None
                ),
                "left_arm_q": left_arm_q.tolist() if left_arm_q is not None else None,
            },
            # NOTE: as requested, not including 'q' or 'joint_names' here
        }

    # -------------------------
    # Recording
    # -------------------------
    def start_recording(self) -> bool:
        if not self.connected:
            return False
        with self._rec_lock:
            self._rec_samples.clear()
            self._rec_active = True
            try:
                if self.model is not None:
                    self._rec_joint_names = list(self.model.robot_joint_names)
            except Exception:
                self._rec_joint_names = None
        return True

    def stop_recording(self) -> dict:
        with self._rec_lock:
            self._rec_active = False
            count = len(self._rec_samples)
            elapsed_ms = (
                int(Settings.master_arm_loop_period * count * 1000) if count else 0
            )
            names = list(self._rec_joint_names) if self._rec_joint_names else None
        return {"count": count, "elapsed_ms": elapsed_ms, "joint_names": names}

    def recording_state(self) -> dict:
        with self._rec_lock:
            active = self._rec_active
            count = len(self._rec_samples)
            elapsed_ms = (
                int(Settings.master_arm_loop_period * count * 1000) if count else 0
            )
        return {"active": active, "count": count, "elapsed_ms": elapsed_ms}

    def build_recording_csv(self) -> tuple[str, bytes]:
        with self._rec_lock:
            rows = list(self._rec_samples)
            names = list(self._rec_joint_names) if self._rec_joint_names else None
        if not rows:
            header = ["time"]
        else:
            dim = len(rows[0]) - 1
            header = ["time"] + (
                names if names and len(names) == dim else [f"q{i}" for i in range(dim)]
            )
        out = [",".join(header)]
        for r in rows:
            out.append(",".join(str(x) for x in r))
        csv_str = "\n".join(out)
        fname = f"recording_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        return fname, csv_str.encode("utf-8")

    def build_recording_summary(self) -> dict:
        with self._rec_lock:
            rows = list(self._rec_samples)
            names = list(self._rec_joint_names) if self._rec_joint_names else None
        if not rows:
            return {"joint_names": names or [], "dt": 0.0, "frames": []}
        frames = [r[1:] for r in rows]
        return {
            "joint_names": names or [f"q{i}" for i in range(len(frames[0]))],
            "dt": Settings.master_arm_loop_period,
            "frames": frames,
        }

    # -------------------------
    # Playback (Play mode)
    # -------------------------
    def set_play_evaluator(
        self, eval_range: EvalRangeFn, eval_at: Optional[EvalAtFn] = None
    ):
        """
        Inject timeline evaluators from outside.
        - eval_range(t0_ms, t1_ms, step_ms) -> [q...]  [REQUIRED for start]
        - eval_at(t_ms) -> q  [OPTIONAL, used in loop if provided]
        """
        self._eval_range = eval_range
        self._eval_at = eval_at

    def can_play(self) -> Tuple[bool, str]:
        if not self.connected:
            return False, "Robot not connected"
        if not self.ready:
            return False, "Robot not ready"
        if self.teleop_active:
            return False, "Teleop is running"
        if self._eval_range is None:
            return False, "No eval_range() is set"
        return True, ""

    def start_play(self, *, t0_ms: float = 0.0) -> bool:
        """
        Start playback:
        1) Query start pose via eval_range(t0,t0,step) and pre-roll to it in 2.0s
        2) Spawn loop that tracks the playhead and sends commands every master_arm_loop_period
        """
        ok, reason = self.can_play()
        if not ok:
            return False

        try:
            # Fetch the exact starting pose using eval_range
            samples = self._eval_range(
                float(t0_ms), float(t0_ms), 1.0
            )  # step doesn't matter for single sample
            if not samples:
                return False
            q_start = np.asarray(samples[0], dtype=float)

            # Clamp to limits if available
            try:
                q_start = np.clip(q_start, self.robot_min_q, self.robot_max_q)
            except Exception:
                pass

            # Pre-roll: single position command with minimum_time=2.0s
            cmd = self._build_position_command_from_q(q_start, min_time_s=2.0)
            fb = self.robot.send_command(cmd).get()
            if fb.finish_code != rby.RobotCommandFeedback.FinishCode.Ok:
                return False
        except Exception:
            return False

        with self._play_lock:
            if self.playing:
                return True  # idempotent
            self._play_stop.clear()
            self._play_marker_ms = float(t0_ms)
            self._play_thread = threading.Thread(target=self._run_play, daemon=True)
            self.playing = True
            self._play_thread.start()
        return True

    def seek(self, marker_ms: float) -> bool:
        try:
            with self._play_lock:
                if self.playing:
                    return False
                
                self._play_marker_ms = max(0.0, float(marker_ms))
            return True
        except Exception:
            return False

    def stop_play(self) -> None:
        with self._play_lock:
            if not self.playing:
                return
            self._play_stop.set()
        if self._play_thread:
            try:
                self._play_thread.join(timeout=1.0)
            except Exception:
                pass
        with self._play_lock:
            self.playing = False
            self._play_thread = None

    def play_state(self) -> dict:
        return {
            "playing": self.playing,
            "marker_ms": int(self._play_marker_ms),
            "teleop_active": self.teleop_active,
            "connected": self.connected,
            "ready": self.ready,
        }

    def _run_play(self):
        """
        Playback loop:
        - Period = Settings.master_arm_loop_period (seconds)
        - Prefer eval_at(t_ms) for single-shot sampling if provided;
          else sample a short horizon via eval_range and consume the first.
        """
        period_s = float(Settings.master_arm_loop_period)
        period_ms = period_s * 1000.0

        # establish a stable schedule
        start_wall = time.time()
        k = 0  # tick index
        try:
            self.create_stream()  # optional
        except Exception:
            self._play_stop.set()

        try:
            while not self._play_stop.is_set():
                t_ms = self._play_marker_ms + period_ms

                q = None
                try:
                    if self._eval_at is not None:
                        q = self._eval_at(float(t_ms))
                    else:
                        block = self._eval_range(float(t_ms), float(t_ms), period_ms)
                        if block:
                            q = np.asarray(block[0], dtype=float)
                except Exception:
                    q = None

                if q is not None:
                    try:
                        # clamp and send
                        try:
                            q = np.clip(q, self.robot_min_q, self.robot_max_q)
                        except Exception:
                            pass
                        cmd = self._build_position_command_from_q(
                            q, min_time_s=period_s * 1.01
                        )
                        self.stream.send_command(cmd)
                    except Exception:
                        self._play_stop.set()
                        break

                # advance marker & wait until next tick
                self._play_marker_ms = t_ms
                k += 1

                # sleep to maintain loop period
                next_time = start_wall + k * period_s
                now = time.time()
                delay = next_time - now
                if delay > 0:
                    time.sleep(delay)
                else:
                    # we're late; don't sleep to catch up
                    pass

        finally:
            with self._play_lock:
                self.playing = False


ROBOT = RobotManager()
