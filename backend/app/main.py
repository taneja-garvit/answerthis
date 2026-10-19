from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.base import LLMProvider
from app.ai.factory import build_llm_provider
from app.api.errors import register_error_handlers
from app.api.middleware import RequestIDMiddleware
from app.api.router import api_router, health_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database, create_engine_from_url
from app.papers.base import PaperProvider
from app.papers.factory import build_http_client, build_paper_providers


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    *,
    llm: LLMProvider | None = None,
    paper_providers: list[PaperProvider] | None = None,
) -> FastAPI:
    """App factory. Run with: uvicorn app.main:create_app --factory

    Startup never touches the schema; migrations are applied with Alembic.
    Tests inject `llm` and `paper_providers` with mocked transports."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    if database is None:
        database = Database(create_engine_from_url(settings.require_database_url(), settings))
    llm = llm or build_llm_provider(settings)
    http_client = None
    if paper_providers is None:
        http_client = build_http_client(settings)
        paper_providers = build_paper_providers(settings, http_client)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await llm.aclose()
        if http_client is not None:
            await http_client.aclose()
        await database.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = database
    app.state.llm = llm
    app.state.paper_providers = paper_providers

    app.add_middleware(RequestIDMiddleware)
    # Added last, so outermost: CORS headers are applied even to the 500
    # envelope produced by RequestIDMiddleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)
    return app
