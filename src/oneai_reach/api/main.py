"""FastAPI application factory and main entry point."""

import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from oneai_reach.api.middleware import setup_exception_handlers, setup_middleware
from oneai_reach.api.models import HealthResponse
from oneai_reach.api.v1.admin import router as admin_router
from oneai_reach.api.v1.agents import router as agents_router
from oneai_reach.api.v1.channels import router as channels_router
from oneai_reach.api.v1.contacts import router as contacts_router
from oneai_reach.api.v1.legacy import router as legacy_router
from oneai_reach.api.v1.mcp import router as mcp_router
from oneai_reach.api.v1.personas import router as personas_router
from oneai_reach.api.v1.products import router as products_router
from oneai_reach.api.v1.webhooks import router as webhooks_router
from oneai_reach.api.webhooks import capi_router, waha_router
from oneai_reach.config.settings import get_settings

logger = logging.getLogger(__name__)

_project = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def create_app() -> FastAPI:
    app = FastAPI(
        title="1ai-reach API",
        description="Cold outreach automation pipeline for BerkahKarya",
        version="1.0.0",
    )

    settings = get_settings()

    # Run V2 migration (workspaces + channels) on startup
    try:
        from oneai_reach.infrastructure.database.migration_v2 import run_migration
        db_path = os.path.join(_project, "data", "leads.db")
        if os.path.exists(db_path):
            run_migration(db_path)
    except Exception as e:
        logger.error(f"V2 migration failed: {e}")

    # Run persona migration (personas + assignments)
    try:
        from oneai_reach.infrastructure.database.migration_personas import run_persona_migration
        if os.path.exists(db_path):
            run_persona_migration(db_path)
        else:
            logger.warning(f"DB not found at {db_path}, skipping persona migration")
    except Exception as e:
        logger.error(f"Persona migration failed: {e}")
        raise

    setup_middleware(app)
    setup_exception_handlers(app)

    app.include_router(waha_router)
    app.include_router(capi_router)
    app.include_router(webhooks_router)
    app.include_router(mcp_router)
    app.include_router(admin_router)
    app.include_router(agents_router)
    app.include_router(channels_router)
    app.include_router(contacts_router)
    app.include_router(personas_router)
    app.include_router(products_router)
    app.include_router(legacy_router, prefix="/api/v1/legacy")

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data")
    if os.path.isdir(data_dir):
        app.mount("/data", StaticFiles(directory=data_dir), name="static-data")

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

    @app.get("/", tags=["redirect"])
    async def root_redirect():
        """Redirect root to dashboard."""
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/dashboard", status_code=302)

    return app


# Create app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
