"""FastAPI application factory and main entry point.

Creates and configures the FastAPI application with all middleware,
exception handlers, and routes.
"""

from fastapi import FastAPI

from oneai_reach.api.middleware import setup_exception_handlers, setup_middleware
from oneai_reach.api.models import HealthResponse
from oneai_reach.api.v1.admin import router as admin_router
from oneai_reach.api.v1.agents import router as agents_router
from oneai_reach.api.v1.mcp import router as mcp_router
from oneai_reach.api.webhooks import capi_router, waha_router
from oneai_reach.config.settings import get_settings


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="1ai-reach API",
        description="Cold outreach automation pipeline for BerkahKarya",
        version="1.0.0",
    )

    settings = get_settings()

    setup_middleware(app)
    setup_exception_handlers(app)

    app.include_router(waha_router)
    app.include_router(capi_router)
    app.include_router(mcp_router)
    app.include_router(admin_router)
    app.include_router(agents_router)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            version="1.0.0",
        )

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    async def health_check_v1() -> HealthResponse:
        """Health check endpoint (v1 API)."""
        return HealthResponse(
            status="healthy",
            version="1.0.0",
        )

    return app


# Create app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
