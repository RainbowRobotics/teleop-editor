# backend/app/robot/gripper.py
import threading, time
from typing import Optional, Dict, Any, List
import numpy as np
import rby1_sdk as rby


class Gripper:
    """
    Two-finger Dynamixel gripper (IDs 0,1). Normalized target is [right, left].
    """

    INF = 1.0e9
    GRIPPER_DIRECTION = False  # False: 0=open, 1=close (invert mapping)

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.bus: Optional[rby.DynamixelBus] = None
        self.connected = False
        self.homed = False

        self.min_q = np.array([self.INF, self.INF], dtype=np.float64)
        self.max_q = np.array([-self.INF, -self.INF], dtype=np.float64)
        self.target_q: Optional[np.ndarray] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ---- connect / disconnect ----
    def connect(self, verbose: bool = False) -> bool:
        with self._lock:
            if self.connected:
                return True
            self.bus = rby.DynamixelBus(rby.upc.GripperDeviceName)
            self.bus.open_port()
            self.bus.set_baud_rate(2_000_000)
            self.bus.set_torque_constant([1, 1])

            ids = [0, 1]
            ok = True
            for i in ids:
                if not self.bus.ping(i):
                    if verbose:
                        print(f"[Gripper] Dynamixel ID {i} is not active")
                    ok = False
                elif verbose:
                    print(f"[Gripper] Dynamixel ID {i} is active")
            if not ok:
                try:
                    self.bus.close_port()
                except Exception:
                    pass
                self.bus = None
                return False

            self.bus.group_sync_write_torque_enable([(i, 1) for i in ids])
            self.connected = True
            return True

    def disconnect(self):
        with self._lock:
            self.stop()
            if self.bus:
                try:
                    self.bus.group_sync_write_torque_enable([(0, 0), (1, 0)])
                except Exception:
                    pass
                try:
                    self.bus.close_port()
                except Exception:
                    pass
            self.bus = None
            self.connected = False
            self.homed = False
            self.min_q[:] = self.INF
            self.max_q[:] = -self.INF
            self.target_q = None

    def _set_mode(self, mode: int):
        ids = [0, 1]
        self.bus.group_sync_write_torque_enable([(i, 0) for i in ids])
        self.bus.group_sync_write_operating_mode([(i, mode) for i in ids])
        self.bus.group_sync_write_torque_enable([(i, 1) for i in ids])

    # ---- homing ----
    def homing(self, timeout_s: float = 10.0) -> bool:
        with self._lock:
            if not self.connected:
                return False
            self._set_mode(rby.DynamixelBus.CurrentControlMode)

        ids = [0, 1]
        q = np.zeros(2, dtype=np.float64)
        prev = q.copy()
        self.min_q[:] = self.INF
        self.max_q[:] = -self.INF
        dir_idx = 0
        still = 0
        t0 = time.time()

        while dir_idx < 2:
            with self._lock:
                if not self.connected:
                    return False
                self.bus.group_sync_write_send_torque(
                    [(i, 0.5 if dir_idx == 0 else -0.5) for i in ids]
                )
                rv = self.bus.group_fast_sync_read_encoder(ids)
            if rv is not None:
                for dev_id, enc in rv:
                    q[dev_id] = enc
            self.min_q = np.minimum(self.min_q, q)
            self.max_q = np.maximum(self.max_q, q)
            if np.allclose(prev, q, atol=[10, 10]):
                still += 1
            else:
                still = 0
            prev[:] = q
            if still >= 30:
                dir_idx += 1
                still = 0
            if (time.time() - t0) > timeout_s:
                break
            time.sleep(0.1)

        with self._lock:
            try:
                self.bus.group_sync_write_send_torque([(i, 0.0) for i in ids])
            except Exception:
                pass
        ok = (
            np.isfinite(self.min_q).all()
            and np.isfinite(self.max_q).all()
            and np.all(self.max_q > self.min_q)
        )
        self.homed = bool(ok)
        return self.homed

    # ---- loop ----
    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            if not self.connected:
                raise RuntimeError("Gripper not connected")
            self._set_mode(rby.DynamixelBus.CurrentBasedPositionControlMode)
            self.bus.group_sync_write_send_torque([(0, 5.0), (1, 5.0)])
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        with self._lock:
            self._thread = None
            if self.bus:
                try:
                    self.bus.group_sync_write_send_torque([(0, 0.0), (1, 0.0)])
                except Exception:
                    pass

    def _loop(self):
        while True:
            with self._lock:
                if not (self._running and self.connected and self.bus):
                    break
                if self.target_q is not None:
                    pairs = [(i, float(self.target_q[i])) for i in (0, 1)]
                    self.bus.group_sync_write_send_position(pairs)
            time.sleep(0.05)

    # ---- targets ----
    def set_target_normalized_vec(self, n: List[float]):
        arr = np.asarray(n, dtype=np.float64)
        if arr.shape != (2,):
            raise ValueError("n must be [right, left]")
        with self._lock:
            if not (np.isfinite(self.min_q).all() and np.isfinite(self.max_q).all()):
                raise RuntimeError("Homing not done")
            arr = np.clip(arr, 0.0, 1.0)
            span = self.max_q - self.min_q
            if not np.all(span > 0):
                raise RuntimeError("Invalid span")
            tgt = self.min_q + (arr if self.GRIPPER_DIRECTION else (1.0 - arr)) * span
            self.target_q = tgt

    # --- target_n ---
    def get_target_normalized_vec(self) -> Optional[List[float]]:
        target_n = None
        with self._lock:
            if (
                self.target_q is not None
                and np.isfinite(self.min_q).all()
                and np.isfinite(self.max_q).all()
            ):
                span = np.where(
                    (self.max_q - self.min_q) == 0, 1.0, (self.max_q - self.min_q)
                )
                norm = (self.target_q - self.min_q) / span
                target_n = (
                    (norm if self.GRIPPER_DIRECTION else (1.0 - norm))
                    .astype(float)
                    .tolist()
                )
        return target_n

    # ---- state ----
    def state(self) -> Dict[str, Any]:
        target_n = self.get_target_normalized_vec()
        with self._lock:
            return {
                "connected": self.connected,
                "homed": self.homed,
                "running": self._running,
                "min_q": self.min_q.tolist(),
                "max_q": self.max_q.tolist(),
                "target_q": (
                    None
                    if self.target_q is None
                    else self.target_q.astype(float).tolist()
                ),
                "target_n": target_n,  # [right, left]
            }


# singleton
GRIPPER = Gripper()
