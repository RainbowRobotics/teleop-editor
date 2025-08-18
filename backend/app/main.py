import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import quest, robot, ws, motion as motion_ws
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

    # Include routers
    app.include_router(ws.router)
    app.include_router(quest.router)
    app.include_router(robot.router)
    app.include_router(motion_ws.router)
    app.include_router(project_router.router)

    @app.on_event("shutdown")
    def _shutdown():
        quest_service.stop_udp_listener()

    return app


app = create_app()
