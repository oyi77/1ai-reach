"""Middleware for FastAPI application.

Includes CORS, request logging, correlation IDs, and global exception handling.
"""

import logging
import time
import uuid
from collections import defaultdict
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from oneai_reach.config.settings import get_settings
from oneai_reach.domain.exceptions import OneAIReachException

logger = logging.getLogger(__name__)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Add correlation ID to each request for tracing."""

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log incoming requests and outgoing responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", "unknown")

        logger.info(
            f"[{correlation_id}] {request.method} {request.url.path}",
            extra={"correlation_id": correlation_id},
        )

        response = await call_next(request)

        logger.info(
            f"[{correlation_id}] {request.method} {request.url.path} -> {response.status_code}",
            extra={"correlation_id": correlation_id},
        )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using sliding window per IP."""

    def __init__(self, app, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_times = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_rate_limited(self, client_ip: str) -> bool:
        now = time.time()
        window_start = now - 60

        self.request_times[client_ip] = [
            req_time
            for req_time in self.request_times[client_ip]
            if req_time > window_start
        ]

        if len(self.request_times[client_ip]) >= self.requests_per_minute:
            return True

        self.request_times[client_ip].append(now)
        return False

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        if request.url.path in ["/health", "/api/v1/health"]:
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        if self._is_rate_limited(client_ip):
            return JSONResponse(
                status_code=429,
                content={
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute.",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the FastAPI app."""
    settings = get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    if settings.api.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=settings.api.rate_limit_per_minute,
        )


def setup_exception_handlers(app: FastAPI) -> None:
    """Configure global exception handlers."""

    @app.exception_handler(OneAIReachException)
    async def domain_exception_handler(request: Request, exc: OneAIReachException):
        correlation_id = getattr(request.state, "correlation_id", "unknown")

        logger.error(
            f"[{correlation_id}] Domain exception: {exc}",
            extra={"correlation_id": correlation_id},
        )

        return JSONResponse(
            status_code=400,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "type": exc.__class__.__name__,
                "context": exc.context,
                "correlation_id": correlation_id,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        correlation_id = getattr(request.state, "correlation_id", "unknown")

        logger.error(
            f"[{correlation_id}] Unhandled exception: {exc}",
            extra={"correlation_id": correlation_id},
            exc_info=True,
        )

        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "type": "Exception",
                "correlation_id": correlation_id,
            },
        )
