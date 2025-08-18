from fastapi import APIRouter
from app.models import RobotConnectReq, SimpleOkResponse
from app.services.robot_service import robot_service

router = APIRouter(prefix="", tags=["robot"])


@router.post("/robot/connect", response_model=SimpleOkResponse)
async def connect_robot(req: RobotConnectReq) -> SimpleOkResponse:
    """
    Connect to the robot at the specified address.

    :param req: Request containing the robot address.
    :return: Response indicating success or failure of the connection.
    """
    ok = robot_service.connect(req.address)
    return SimpleOkResponse(ok=ok, error=None if ok else "Failed to connect to robot")


@router.post("/robot/disconnect", response_model=SimpleOkResponse)
async def disconnect_robot() -> SimpleOkResponse:
    """
    Disconnect from the robot.

    :return: Response indicating success or failure of the disconnection.
    """
    robot_service.disconnect()
    return SimpleOkResponse(ok=True, error=None)
