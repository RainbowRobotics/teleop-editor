import numpy as np
from dataclasses import dataclass


class Settings:
    master_arm_loop_period = 1 / 100
    
    impedance_stiffness = 30
    impedance_damping_ratio = 1.0
    impedance_torque_limit = 10.0
    
    torso_impedance_stiffness = 400
    torso_impedance_damping_ratio = 1.0
    torso_impedance_torque_limit = 600


@dataclass
class Pose:
    toros: np.ndarray
    right_arm: np.ndarray
    left_arm: np.ndarray


# Model is fixed as "A", but keeping map for clarity
READY_POSE = {
    "A": Pose(
        toros=np.deg2rad([0.0, 45.0, -90.0, 45.0, 0.0, 0.0]),
        right_arm=np.deg2rad([0.0, -5.0, 0.0, -120.0, 0.0, 70.0, 0.0]),
        left_arm=np.deg2rad([0.0, 5.0, 0.0, -120.0, 0.0, 70.0, 0.0]),
    )
}
