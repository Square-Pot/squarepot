# SPDX-License-Identifier: AGPL-3.0-or-later
"""The FastAPI application."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from squarepot_server import __version__, web
from squarepot_server.api import photo_routes, routes
from squarepot_server.api.models import Error
from squarepot_server.config import Settings, get_settings
from squarepot_server.runtime import Runtime
from squarepot_server.store import CollectionStore

ERROR_CODES = {
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_413_CONTENT_TOO_LARGE: "too_large",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "invalid_request",
    status.HTTP_429_TOO_MANY_REQUESTS: "too_many_requests",
    status.HTTP_503_SERVICE_UNAVAILABLE: "store_unavailable",
}


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = Error(code=code, message=message)
    return JSONResponse(body.model_dump(), status_code=status_code)


async def on_http_error(request: Request, exc: HTTPException) -> JSONResponse:
    code = ERROR_CODES.get(exc.status_code, "error")
    response = error_response(exc.status_code, code, str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def on_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Starlette logs the traceback; the client gets no internals.
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Internal server error."
    )


async def on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    message = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    )
    return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_request", message)


def operation_id(route: APIRoute) -> str:
    """Use the handler's name as the operation id, for readable generated clients."""
    return route.name


def api_docs_from_environment() -> bool:
    """SQUAREPOT_API_DOCS, read without the other settings, which may not be set yet."""
    return os.environ.get("SQUAREPOT_API_DOCS", "").strip().lower() in ("1", "true", "yes", "on")


def create_app(settings: Settings | None = None, store: CollectionStore | None = None) -> FastAPI:
    """Build the app. Settings come from the environment unless given; tests pass a fake store."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = Runtime.start(settings or get_settings(), store)
        app.state.runtime = runtime
        try:
            yield
        finally:
            runtime.stop()

    # The interactive API docs and the live schema are off unless asked for: the
    # contract is server/openapi.json in the repository.
    docs = settings.api_docs if settings else api_docs_from_environment()
    app = FastAPI(
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
        title="Square-Pot API",
        version=__version__,
        summary="Plant collections kept in Google Sheets, looked up by label number.",
        license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
        generate_unique_id_function=operation_id,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_exception_handler(HTTPException, on_http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, on_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, on_unexpected_error)
    app.include_router(routes.public)
    app.include_router(routes.router)
    app.include_router(photo_routes.public)
    app.include_router(photo_routes.router)
    # The web app answers whatever no route matches, routes added later included.
    app.router.default = web.serve
    return app
