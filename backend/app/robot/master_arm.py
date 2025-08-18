# backend/app/robot/master_arm.py
import os, time
from typing import Optional, Dict, Any, Callable
import rby1_sdk as rby
from .common import Settings


class MasterArmManager:
    """
    RBY Master Arm wrapper (connect + start/stop control).
    The actual control callback is provided by teleop.
    """

    def __init__(self) -> None:
        self.device = rby.upc.MasterArmDeviceName
        self.master: Optional[rby.upc.MasterArm] = None
        self.connected = False
        self.running = False

    def connect(self) -> bool:
        print(self.device)
        rby.upc.initialize_device(self.device)
        model_path = f"{os.path.dirname(os.path.realpath(__file__))}/master_arm.urdf"
        self.master = rby.upc.MasterArm(self.device)
        self.master.set_model_path(model_path)
        self.master.set_control_period(Settings.master_arm_loop_period)
        active = self.master.initialize(verbose=True)
        ok = len(active) == rby.upc.MasterArm.DeviceCount
        self.connected = bool(ok)
        return self.connected

    def start_control(
        self, cb: Callable[[rby.upc.MasterArm.State], rby.upc.MasterArm.ControlInput]
    ):
        if not self.connected:
            raise RuntimeError("Master not connected")
        if self.running:
            return
        self.master.start_control(cb)
        self.running = True

    def stop_control(self):
        if not self.running:
            return
        try:
            self.master.stop_control()
        finally:
            self.running = False

    def disconnect(self):
        self.stop_control()
        self.connected = False

    def state(self) -> Dict[str, Any]:
        return {
            "device": self.device,
            "connected": self.connected,
            "running": self.running,
        }


MASTER = MasterArmManager()
