"""Application factory: `uvicorn app.main:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from arq.connections import ArqRedis
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

from app import __version__
from app.api.v1 import api_router
from app.api.v1.google import FLOW_SECONDS, PENDING_SECONDS
from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.email.mailer import QueueMailer, UnconfiguredMailer
from app.errors import document_problem_responses, install_error_handlers
from app.logging_config import configure_logging
from app.middleware import RequestContextMiddleware
from app.redis_client import create_redis
from app.security.google import GoogleClient, OneTimeStore
from app.security.passwords import Passwords
from app.security.rate_limit import RateLimiter
from app.security.sessions import SessionStore
from app.storage import create_storage

API_PREFIX = "/api/v1"


def _operation_id(route: APIRoute) -> str:
    """Stable, readable operation ids for the generated frontend types."""
    return route.name


class WinnowAPI(FastAPI):
    def openapi(self) -> dict[str, Any]:
        if not self.openapi_schema:
            schema = get_openapi(
                title=self.title,
                version=self.version,
                summary=self.summary,
                routes=self.routes,
            )
            self.openapi_schema = document_problem_responses(schema)
        return self.openapi_schema


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        redis = create_redis(settings)
        queue = ArqRedis.from_url(settings.redis_url)  # arq pickles jobs: needs a bytes client
        http = httpx.AsyncClient(timeout=10.0, follow_redirects=False)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.redis = redis
        app.state.queue = queue
        app.state.http = http
        app.state.sessions = SessionStore(redis, settings)
        app.state.rate_limiter = RateLimiter(redis)
        app.state.passwords = Passwords(settings)
        app.state.storage = create_storage(settings)
        app.state.mailer = QueueMailer(queue) if settings.email_enabled else UnconfiguredMailer()
        app.state.google = (
            GoogleClient(
                http,
                settings.google_client_id or "",
                settings.google_client_secret.get_secret_value()
                if settings.google_client_secret
                else "",
            )
            if settings.google_enabled
            else None
        )
        app.state.google_flows = OneTimeStore(redis, "google-flow", FLOW_SECONDS)
        app.state.google_pending = OneTimeStore(redis, "google-2fa", PENDING_SECONDS)
        try:
            yield
        finally:
            await http.aclose()
            await queue.aclose()
            await redis.aclose()
            await engine.dispose()

    app = WinnowAPI(
        title="Winnow API",
        version=__version__,
        summary="Screening for systematic, scoping and rapid reviews.",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.docs_enabled else None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    install_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_router, prefix=API_PREFIX)
    return app
