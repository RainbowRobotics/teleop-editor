import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import traceback

from app.routers import (
    quest,
    robot,
    master,
    teleop,
    ws,
    gripper,
    record,
    play,
    motion as motion_ws,
)
from app.routers import project as project_router
from app.services.quest_service import quest_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    :return: Configured FastAPI application instance.
    """
    app = FastAPI(title="Teleop Editor API", version="1.0.0")

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # 로그 남기기
        logging.error(f"Unhandled exception: {exc}")
        traceback.print_exc()

        # HTTPException은 그대로 전달
        if isinstance(exc, HTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )

        # 나머지 일반 Exception → 500 JSON 반환
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc) or "Internal Server Error"},
        )

    # Include routers
    app.include_router(ws.router)
    app.include_router(quest.router)
    app.include_router(robot.router)
    app.include_router(master.router)
    app.include_router(teleop.router)
    app.include_router(gripper.router)
    app.include_router(record.router)
    app.include_router(play.router)
    app.include_router(motion_ws.router)
    app.include_router(project_router.router)

    @app.on_event("shutdown")
    def _shutdown():
        quest_service.stop_udp_listener()

    return app


app = create_app()
