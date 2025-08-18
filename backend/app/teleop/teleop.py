# backend/app/teleop/teleop.py
import numpy as np, datetime, time
from typing import Dict, Any
import rby1_sdk as rby
from app.robot.robot import ROBOT
from app.robot.master_arm import MASTER
from app.robot.gripper import GRIPPER
from app.robot.common import Settings


class TeleopManager:
    def __init__(self) -> None:
        self.running = False
        self.position_mode = (
            True  # 'position' or 'impedance' -> we keep True by default
        )

        # timers
        self.right_minimum_time = 1.0
        self.left_minimum_time = 1.0

        # latched
        self.right_q = None
        self.left_q = None

    def start(self, control_mode: str = "position"):
        if self.running:
            return
        if not (ROBOT.connected and ROBOT.ready):
            raise RuntimeError("Robot not ready")
        if not MASTER.connected:
            raise RuntimeError("Master not connected")

        self.position_mode = control_mode == "position"
        self.right_q = None
        self.left_q = None
        self.right_minimum_time = 1.0
        self.left_minimum_time = 1.0

        # ensure gripper up
        if not GRIPPER.connected:
            if not GRIPPER.connect(verbose=True):
                raise RuntimeError("Gripper connect failed")
            if not GRIPPER.homing():
                raise RuntimeError("Gripper homing failed")
            GRIPPER.start()

        if not ROBOT.create_stream():
            raise RuntimeError("Cannot create stream")

        ROBOT.stream.send_command(ROBOT.build_ready_command(control_mode == "position", 1e6))

        def loop(state: rby.upc.MasterArm.State):
            # latch
            if self.right_q is None:
                self.right_q = state.q_joint[0:7]
            if self.left_q is None:
                self.left_q = state.q_joint[7:14]

            # gripper via triggers (0..1000 => 0..1)
            GRIPPER.set_target_normalized_vec(
                [
                    float(state.button_right.trigger) / 1000.0,
                    float(state.button_left.trigger) / 1000.0,
                ]
            )

            # assist torque (copied from your script)
            ma_q_limit_barrier = 0.5
            ma_min_q = np.deg2rad(
                [-360, -30, 0, -135, -90, 35, -360, -360, 10, -90, -135, -90, 35, -360]
            )
            ma_max_q = np.deg2rad(
                [360, -10, 90, -60, 90, 80, 360, 360, 30, 0, -60, 90, 80, 360]
            )
            ma_torque_limit = np.array([4.0] * 14)
            ma_viscous_gain = np.array([0.02, 0.02, 0.02, 0.02, 0.01, 0.01, 0.002] * 2)

            torque = (
                state.gravity_term
                + ma_q_limit_barrier
                * (
                    np.maximum(ma_min_q - state.q_joint, 0)
                    + np.minimum(ma_max_q - state.q_joint, 0)
                )
                + ma_viscous_gain * state.qvel_joint
            )
            torque = np.clip(torque, -ma_torque_limit, ma_torque_limit)

            # operating mode per side
            if state.button_right.button == 1:
                mode_r = rby.DynamixelBus.CurrentControlMode
                self.right_q = state.q_joint[0:7]
                tgt_torque_r = torque[0:7]
                tgt_pos_r = None
            else:
                mode_r = rby.DynamixelBus.CurrentBasedPositionControlMode
                tgt_torque_r = np.array([5] * 7)
                tgt_pos_r = self.right_q

            if state.button_left.button == 1:
                mode_l = rby.DynamixelBus.CurrentControlMode
                self.left_q = state.q_joint[7:14]
                tgt_torque_l = torque[7:14]
                tgt_pos_l = None
            else:
                mode_l = rby.DynamixelBus.CurrentBasedPositionControlMode
                tgt_torque_l = np.array([5] * 7)
                tgt_pos_l = self.left_q

            # collision check
            q = ROBOT.robot_q.copy()
            q[ROBOT.model.right_arm_idx] = self.right_q
            q[ROBOT.model.left_arm_idx] = self.left_q
            ROBOT.dyn_state.set_q(q)
            ROBOT.dyn_model.compute_forward_kinematics(ROBOT.dyn_state)
            is_collision = (
                ROBOT.dyn_model.detect_collisions_or_nearest_links(ROBOT.dyn_state, 1)[
                    0
                ].distance
                < 0.02
            )

            # build robot command
            rc = rby.BodyComponentBasedCommandBuilder()

            if state.button_right.button and not is_collision:
                self.right_minimum_time = max(
                    self.right_minimum_time - Settings.master_arm_loop_period,
                    Settings.master_arm_loop_period * 1.01,
                )
                right_builder = (
                    rby.JointPositionCommandBuilder()
                    if self.position_mode
                    else rby.JointImpedanceControlCommandBuilder()
                )
                (
                    right_builder.set_command_header(
                        rby.CommandHeaderBuilder().set_control_hold_time(1e6)
                    )
                    .set_position(
                        np.clip(
                            self.right_q,
                            ROBOT.robot_min_q[ROBOT.model.right_arm_idx],
                            ROBOT.robot_max_q[ROBOT.model.right_arm_idx],
                        )
                    )
                    .set_velocity_limit(ROBOT.robot_max_qdot[ROBOT.model.right_arm_idx])
                    .set_acceleration_limit(
                        ROBOT.robot_max_qddot[ROBOT.model.right_arm_idx] * 30
                    )
                    .set_minimum_time(self.right_minimum_time)
                )
                if not self.position_mode:
                    (
                        right_builder.set_stiffness(
                            [Settings.impedance_stiffness]
                            * len(ROBOT.model.right_arm_idx)
                        )
                        .set_damping_ratio(Settings.impedance_damping_ratio)
                        .set_torque_limit(
                            [Settings.impedance_torque_limit]
                            * len(ROBOT.model.right_arm_idx)
                        )
                    )
                rc.set_right_arm_command(right_builder)
            else:
                self.right_minimum_time = 0.8

            if state.button_left.button and not is_collision:
                self.left_minimum_time = max(
                    self.left_minimum_time - Settings.master_arm_loop_period,
                    Settings.master_arm_loop_period * 1.01,
                )
                left_builder = (
                    rby.JointPositionCommandBuilder()
                    if self.position_mode
                    else rby.JointImpedanceControlCommandBuilder()
                )
                (
                    left_builder.set_command_header(
                        rby.CommandHeaderBuilder().set_control_hold_time(1e6)
                    )
                    .set_position(
                        np.clip(
                            self.left_q,
                            ROBOT.robot_min_q[ROBOT.model.left_arm_idx],
                            ROBOT.robot_max_q[ROBOT.model.left_arm_idx],
                        )
                    )
                    .set_velocity_limit(ROBOT.robot_max_qdot[ROBOT.model.left_arm_idx])
                    .set_acceleration_limit(
                        ROBOT.robot_max_qddot[ROBOT.model.left_arm_idx] * 30
                    )
                    .set_minimum_time(self.left_minimum_time)
                )
                if not self.position_mode:
                    (
                        left_builder.set_stiffness(
                            [Settings.impedance_stiffness]
                            * len(ROBOT.model.left_arm_idx)
                        )
                        .set_damping_ratio(Settings.impedance_damping_ratio)
                        .set_torque_limit(
                            [Settings.impedance_torque_limit]
                            * len(ROBOT.model.left_arm_idx)
                        )
                    )
                rc.set_left_arm_command(left_builder)
            else:
                self.left_minimum_time = 0.8

            ROBOT.stream.send_command(
                rby.RobotCommandBuilder().set_command(
                    rby.ComponentBasedCommandBuilder().set_body_command(rc)
                )
            )

            # return MasterArm control input (modes/torque/pos)
            cin = rby.upc.MasterArm.ControlInput()
            cin.target_operating_mode[0:7].fill(mode_r)
            cin.target_torque[0:7] = tgt_torque_r
            if tgt_pos_r is not None:
                cin.target_position[0:7] = tgt_pos_r
            cin.target_operating_mode[7:14].fill(mode_l)
            cin.target_torque[7:14] = tgt_torque_l
            if tgt_pos_l is not None:
                cin.target_position[7:14] = tgt_pos_l
            return cin

        MASTER.start_control(loop)
        self.running = True

    def stop(self):
        if not self.running:
            return
        try:
            MASTER.stop_control()
            ROBOT.stream.cancel()
        finally:
            self.running = False

    def state(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "mode": ("position" if self.position_mode else "impedance"),
        }


TELEOP = TeleopManager()
