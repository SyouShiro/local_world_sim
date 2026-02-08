from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import branch as branch_api
from app.api import provider as provider_api
from app.api import session as session_api
from app.api import timeline as timeline_api
from app.api import websocket as websocket_api
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.base import create_engine, create_sessionmaker, init_db
from app.services.memory_service import create_memory_service
from app.services.prompt_builder import PromptBuilder
from app.services.branch_service import BranchService
from app.services.provider_service import ProviderService
from app.services.runner import RunnerManager
from app.services.simulation_service import SimulationService


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    setup_logging(settings.log_level)

    engine = create_engine(settings.db_url)
    sessionmaker = create_sessionmaker(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(engine)
        yield
        await app.state.runner_manager.shutdown()
        await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.ws_manager = websocket_api.WebSocketManager()
    app.state.provider_service = ProviderService(sessionmaker, app.state.ws_manager, settings)
    app.state.memory_service = create_memory_service(sessionmaker=sessionmaker, settings=settings)
    app.state.branch_service = BranchService(
        sessionmaker, app.state.ws_manager, app.state.memory_service
    )
    app.state.simulation_service = SimulationService(
        sessionmaker,
        PromptBuilder(
            memory_max_snippets=settings.memory_max_snippets,
            memory_max_chars=settings.memory_max_chars,
        ),
        app.state.provider_service,
        app.state.memory_service,
    )
    app.state.runner_manager = RunnerManager(
        sessionmaker, app.state.simulation_service, app.state.ws_manager
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(session_api.router)
    app.include_router(provider_api.router)
    app.include_router(branch_api.router)
    app.include_router(timeline_api.timeline_router)
    app.include_router(timeline_api.message_router)
    app.include_router(timeline_api.intervention_router)
    app.include_router(websocket_api.router)

    return app


app = create_app()
