import logging
from app.state import State

import rby1_sdk as rby


class RobotService:
    """Service class to manage the robot connection and state."""

    def __init__(self):
        self.robot = None

    def connect(self, address: str) -> bool:
        """Connect to the robot at the specified address."""
        logging.info(f"Connecting to robot at {address}")
        self.robot = rby.create_robot_a(address)
        ok = self.robot.connect()
        State.robot_connected = bool(ok)
        return ok

    def disconnect(self):
        """Disconnect from the robot."""
        if self.robot:
            self.robot.disconnect()
            self.robot = None
            State.robot_connected = False
            logging.info("Disconnected from robot")


robot_service = RobotService()
