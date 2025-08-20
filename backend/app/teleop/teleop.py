# backend/app/teleop/teleop.py
import numpy as np, datetime, time
from typing import Dict, Any
import rby1_sdk as rby
from app.robot.robot import ROBOT
from app.robot.master_arm import MASTER
from app.robot.gripper import GRIPPER
from app.state import State
from app.robot.common import Settings


class TeleopManager:

    QUEST_LPF = 0.98
    MASTER_ARM_TORQUE_GAIN = 0.5
    COLLISION_THRESHOLD = 0.00

    # LIMITS
    LINEAR_VECLOITY_LIMIT = 4.0  # m/s
    ANGULAR_VELOCITY_LIMIT = 12  # rad/s
    ACCELERATION_LIMIT_SCALING = 0.3  #
    DEFAULT_LINEAR_ACCELERATION = 10.0
    DEFAULT_ANGULAR_ACCELERATION = 10.0

    def __init__(self) -> None:
        self.running = False
        self.position_mode = (
            True  # 'position' or 'impedance' -> we keep True by default
        )

        # timers
        self.torso_minimum_time = 1.0
        self.right_minimum_time = 1.0
        self.left_minimum_time = 1.0

        # latched
        self.right_q = None
        self.left_q = None

        # Cache
        self.torso_last_pose = None
        self.torso_ref_pose = None
        self.quest_head_ref_pose = None

        self.quest_head_pose = None
        self.quest_head_position = None
        self.quest_head_quat = None

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
        control_hold_time = 1e6

        # ensure gripper up
        if not GRIPPER.connected:
            if not GRIPPER.connect(verbose=True):
                raise RuntimeError("Gripper connect failed")
            if not GRIPPER.homing():
                raise RuntimeError("Gripper homing failed")
            GRIPPER.start()

        if not ROBOT.create_stream():
            raise RuntimeError("Cannot create stream")

        # 현재 로봇의 상태를 가지고 와서 torso는 Cartesian 명령으로, right_arm/left_arm 은 Joint 명령으로 보냄
        # control_mode에 따라서 다르게 Cartesian/JointPositionImpedance 할지, CartesianControl/JointPosition 이렇게 나눠서 진행

        torso_pose, right_arm_q, left_arm_q = ROBOT.get_current_pose()
        if (torso_pose is None) or (right_arm_q is None) or (left_arm_q is None):
            raise RuntimeError("로봇에서 정보를 가지고 오지 못했습니다.")

        self.torso_last_pose = torso_pose.copy()
        self.torso_ref_pose = self.torso_last_pose.copy()

        self.quest_head_ref_pose = None

        self.quest_head_pose = None
        self.quest_head_position = None
        self.quest_head_quat = None

        # CartesianCommandBuilder와 CartesianImpedanceControlCommandBuilder는 add_target 인자가 조금 다르기 때문에 나눠서 빌더를 생성해 줍니다.
        if self.position_mode:
            torso_builder = (
                rby.CartesianCommandBuilder()
                .set_command_header(
                    rby.CommandHeaderBuilder().set_control_hold_time(control_hold_time)
                )
                .set_stop_joint_position_tracking_error(0)
                .set_stop_orientation_tracking_error(0)
                .set_stop_joint_position_tracking_error(0)
                .add_target(
                    "base",
                    "link_torso_5",
                    torso_pose,
                    self.LINEAR_VECLOITY_LIMIT,
                    self.ANGULAR_VELOCITY_LIMIT,
                    self.ACCELERATION_LIMIT_SCALING,
                )
                .set_minimum_time(5)
            )
        else:
            torso_builder = (
                rby.CartesianImpedanceControlCommandBuilder()
                .set_command_header(
                    rby.CommandHeaderBuilder().set_control_hold_time(control_hold_time)
                )
                .set_joint_stiffness(
                    [Settings.torso_impedance_stiffness] * len(ROBOT.model.torso_idx)
                )
                .set_joint_torque_limit(
                    [Settings.torso_impedance_torque_limit] * len(ROBOT.model.torso_idx)
                )
                .add_joint_limit("torso_1", -0.523598776, 1.3)
                .add_joint_limit("torso_2", -2.617993878, -0.2)
                .set_stop_joint_position_tracking_error(0)
                .set_stop_orientation_tracking_error(0)
                .set_stop_joint_position_tracking_error(0)
                .add_target(
                    "base",
                    "link_torso_5",
                    torso_pose,
                    self.LINEAR_VECLOITY_LIMIT,
                    self.ANGULAR_VELOCITY_LIMIT,
                    self.DEFAULT_LINEAR_ACCELERATION * self.ACCELERATION_LIMIT_SCALING,
                    self.DEFAULT_ANGULAR_ACCELERATION * self.ACCELERATION_LIMIT_SCALING,
                )
                .set_minimum_time(5)
            )

        right_builder = (
            rby.JointPositionCommandBuilder()
            if self.position_mode
            else rby.JointImpedanceControlCommandBuilder()
        )
        (
            right_builder.set_command_header(
                rby.CommandHeaderBuilder().set_control_hold_time(control_hold_time)
            )
            .set_position(right_arm_q)
            .set_minimum_time(5)
        )
        if not self.position_mode:
            (
                right_builder.set_stiffness(
                    [Settings.impedance_stiffness] * len(ROBOT.model.right_arm_idx)
                )
                .set_damping_ratio(Settings.impedance_damping_ratio)
                .set_torque_limit(
                    [Settings.impedance_torque_limit] * len(ROBOT.model.right_arm_idx)
                )
            )

        left_builder = (
            rby.JointPositionCommandBuilder()
            if self.position_mode
            else rby.JointImpedanceControlCommandBuilder()
        )
        (
            left_builder.set_command_header(
                rby.CommandHeaderBuilder().set_control_hold_time(control_hold_time)
            )
            .set_position(left_arm_q)
            .set_minimum_time(5)
        )
        if not self.position_mode:
            (
                left_builder.set_stiffness(
                    [Settings.impedance_stiffness] * len(ROBOT.model.left_arm_idx)
                )
                .set_damping_ratio(Settings.impedance_damping_ratio)
                .set_torque_limit(
                    [Settings.impedance_torque_limit] * len(ROBOT.model.left_arm_idx)
                )
            )

        ROBOT.stream.send_command(
            rby.RobotCommandBuilder().set_command(
                rby.ComponentBasedCommandBuilder().set_body_command(
                    rby.BodyComponentBasedCommandBuilder()
                    .set_torso_command(torso_builder)
                    .set_right_arm_command(right_builder)
                    .set_left_arm_command(left_builder)
                )
            )
        )

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
                [-360, -30, 0, -135, -90, 35, -360, 
                 -360, 10, -90, -135, -90, 35, -360]
            )
            ma_max_q = np.deg2rad(
                [360, -10, 90, -60, 90, 80, 360, 
                 360, 30, 0, -60, 90, 80, 360]
            )
            ma_torque_limit = np.array([3.5, 3.5, 3.5, 1.5, 1.5, 1.5, 1.5] * 2)
            ma_viscous_gain = np.array([0.02, 0.02, 0.02, 0.02, 0.01, 0.01, 0.002] * 2)

            torque = (
                state.gravity_term * self.MASTER_ARM_TORQUE_GAIN
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
                tgt_torque_r = ma_torque_limit[0:7]
                tgt_pos_r = self.right_q

            if state.button_left.button == 1:
                mode_l = rby.DynamixelBus.CurrentControlMode
                self.left_q = state.q_joint[7:14]
                tgt_torque_l = torque[7:14]
                tgt_pos_l = None
            else:
                mode_l = rby.DynamixelBus.CurrentBasedPositionControlMode
                tgt_torque_l = ma_torque_limit[7:14]
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
                < self.COLLISION_THRESHOLD
            )

            # build robot command
            rc = rby.BodyComponentBasedCommandBuilder()

            if (
                State.quest_udp_running
            ):  # TODO 실제로 데이터가 들어오고 있는지 확인이 필요합니다.
                hp = State.quest_head_position
                hq = State.quest_head_quat

                if self.quest_head_position is None:
                    self.quest_head_position = hp
                if self.quest_head_quat is None:
                    self.quest_head_quat = hq

                self.quest_head_position = self.QUEST_LPF * self.quest_head_position + (1 - self.QUEST_LPF) * hp
                self.quest_head_quat = self.QUEST_LPF * self.quest_head_quat + (1 - self.QUEST_LPF) * hq
                T_conv = np.array(
                    [
                        [0, -1, 0, 0],
                        [0, 0, 1, 0],
                        [1, 0, 0, 0],
                        [0, 0, 0, 1],
                    ]
                )
                self.quest_head_pose = (
                    T_conv.T
                    @ State._pose_to_se3(self.quest_head_position, self.quest_head_quat)
                    @ T_conv
                )
                if self.quest_head_ref_pose is None:
                    self.quest_head_ref_pose = self.quest_head_pose.copy()

                if state.button_right.button and state.button_left.button:
                    self.torso_last_pose = (
                        self.torso_ref_pose
                        @ np.linalg.inv(self.quest_head_ref_pose)
                        @ self.quest_head_pose
                    )

                    self.torso_minimum_time = max(
                        self.torso_minimum_time - Settings.master_arm_loop_period,
                        Settings.master_arm_loop_period * 1.01,
                    )

                    if self.position_mode:
                        torso_builder = (
                            rby.CartesianCommandBuilder()
                            .set_command_header(
                                rby.CommandHeaderBuilder().set_control_hold_time(
                                    control_hold_time
                                )
                            )
                            .set_stop_joint_position_tracking_error(0)
                            .set_stop_orientation_tracking_error(0)
                            .set_stop_joint_position_tracking_error(0)
                            .add_target(
                                "base",
                                "link_torso_5",
                                self.torso_last_pose,
                                self.LINEAR_VECLOITY_LIMIT,  # TODO 튜닝 필요합니다.
                                self.ANGULAR_VELOCITY_LIMIT,  # TODO 튜닝 필요합니다.
                                self.ACCELERATION_LIMIT_SCALING,  # TODO 튜닝 필요합니다.
                            )
                            .set_minimum_time(self.torso_minimum_time)
                        )
                    else:
                        torso_builder = (
                            rby.CartesianImpedanceControlCommandBuilder()
                            .set_command_header(
                                rby.CommandHeaderBuilder().set_control_hold_time(
                                    control_hold_time
                                )
                            )
                            .set_joint_stiffness(
                                [Settings.torso_impedance_stiffness]
                                * len(ROBOT.model.torso_idx)
                            )
                            .set_joint_torque_limit(
                                [Settings.torso_impedance_torque_limit]
                                * len(ROBOT.model.torso_idx)
                            )
                            .add_joint_limit("torso_1", -0.523598776, 1.3)
                            .add_joint_limit("torso_2", -2.617993878, -0.2)
                            .set_stop_joint_position_tracking_error(0)
                            .set_stop_orientation_tracking_error(0)
                            .set_stop_joint_position_tracking_error(0)
                            .add_target(
                                "base",
                                "link_torso_5",
                                self.torso_last_pose,
                                self.LINEAR_VECLOITY_LIMIT,  # TODO 튜닝 필요합니다.
                                self.ANGULAR_VELOCITY_LIMIT,  # TODO 튜닝 필요합니다.
                                self.DEFAULT_LINEAR_ACCELERATION
                                * self.ACCELERATION_LIMIT_SCALING,  # TODO 튜닝 필요합니다.
                                self.DEFAULT_ANGULAR_ACCELERATION
                                * self.ACCELERATION_LIMIT_SCALING,  # TODO 튜닝 필요합니다.
                            )
                            .set_minimum_time(self.torso_minimum_time)
                        )
                    rc.set_torso_command(torso_builder)

                else:
                    self.torso_ref_pose = self.torso_last_pose.copy()
                    self.quest_head_ref_pose = self.quest_head_pose.copy()
                    self.torso_minimum_time = 0.8
            else:
                self.quest_head_ref_pose = None
                self.torso_minimum_time = 1.0

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

            try:
                ROBOT.stream.send_command(
                    rby.RobotCommandBuilder().set_command(
                        rby.ComponentBasedCommandBuilder().set_body_command(rc)
                    )
                )
            except:
                pass

            # return MasterArm control input (modes/torque/pos)
            if MASTER.zero_torque:
                tgt_torque_l.fill(0)
                tgt_torque_r.fill(0)
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
        ROBOT.teleop_active = True
        self.running = True

    def stop(self):
        if not self.running:
            return
        try:
            MASTER.stop_control()
            ROBOT.stream.cancel()
        finally:
            ROBOT.teleop_active = False
            self.running = False

    def state(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "mode": ("position" if self.position_mode else "impedance"),
        }


TELEOP = TeleopManager()
