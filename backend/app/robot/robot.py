# backend/app/robot/robot.py
import time, numpy as np
from typing import Optional, Dict, Any, Union, Tuple
import rby1_sdk as rby
from .common import Settings, READY_POSE
import numpy as np
import threading

RobotType = Union[rby.Robot_A, rby.Robot_T5, rby.Robot_M]


class RobotManager:
    """
    Robot connect/power/servo/control-manager & command stream holder.
    """

    BASE_LINK_IDX = 0
    TORSO_5_LINK_IDX = 1

    def __init__(self) -> None:
        self.address: Optional[str] = None
        self.robot: Optional[RobotType] = None
        self.model = None
        self.stream = None

        self.dyn_model = None
        self.dyn_state = None
        self.robot_q = None
        self.robot_min_q = None
        self.robot_max_q = None
        self.robot_max_qdot = None
        self.robot_max_qddot = None

        self._lock = threading.Lock()
        self.update_time = None
        self.torso_pose = None
        self.right_arm_q = None
        self.left_arm_q = None

        self.connected = False
        self.ready = False
        self.power_detail = {}
        self.power_all_on = False
        self.tool_flange_12v = {}
        
        # FOR DEBUGGING
        self.is_simulation = False

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

            # 자세 계산하기
            self.dyn_state.set_q(self.robot_q)
            self.dyn_model.compute_forward_kinematics(self.dyn_state)
            with self._lock:
                self.update_time = time.time()
                self.torso_pose = self.dyn_model.compute_transformation(
                    self.dyn_state, self.BASE_LINK_IDX, self.TORSO_5_LINK_IDX
                )
                self.right_arm_q = self.robot_q[self.model.right_arm_idx]
                self.left_arm_q = self.robot_q[self.model.left_arm_idx]

            try:
                # best effort: map by name, else index keys
                detail = {}
                for i, key in enumerate(["5v", "12v", "24v", "48v"] if not self.is_simulation else ["main"]):
                    detail[key] = state.power_states[i].state == PowerOn
                self.power_detail = detail
                self.power_all_on = all(detail.values()) if detail else False
            except Exception:
                # fallback: at least evaluate "all on" from first state
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

        # 1) power on ALL rails
        if not self.power_all_on:
            if not self.robot.power_on(".*"):  # turns on 5/12/24/48
                return False

        # wait a short moment for power state to reflect
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.power_all_on:
                break
            time.sleep(0.05)

        if not self.power_all_on:
            return False

        time.sleep(0.2)

        # 툴플랜지 12V 전원 인가
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

        # MUST: power all rails + tool 12V both sides
        if not self.ensure_power_and_tools():
            return False

        # Servo on after power rails up
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

        # self.stream = self.robot.create_command_stream(priority=1)

        # go READY pose
        ok = self.move_ready(position_mode=(control_mode == "position"))
        self.ready = bool(
            ok and self.power_all_on and all(self.tool_flange_12v.values())
        )
        return self.ready

    def create_stream(self) -> bool:
        if self.stream is None:
            self.stream = self.robot.create_command_stream(priority=1)
            return True

        if self.stream.is_done():
            self.stream = self.robot.create_command_stream(priority=1)
            return True

        return False

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
            .set_position(pose.toros)
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

    def get_current_pose(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if not self.connected:
            raise RuntimeError("아직 로봇 연결이 안되어있습니다.")

        current_time = time.time()
        with self._lock:
            if (
                (current_time - self.update_time >= 1.0)
                if self.update_time is not None
                else True
            ):
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

    def state(self) -> Dict[str, Any]:
        try:
            torso_pose, right_arm_q, left_arm_q = self.get_current_pose()
        except:
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
            "state": {
                "torso_pose": torso_pose.tolist() if torso_pose is not None else None,
                "right_arm_q": right_arm_q.tolist() if right_arm_q is not None else None,
                "left_arm_q": left_arm_q.tolist() if left_arm_q is not None else None
            }
        }


ROBOT = RobotManager()
