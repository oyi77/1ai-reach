"""Pipeline scripts API endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["pipeline"])


@router.get("/scripts")
async def api_pipeline_scripts():
    PIPELINE_SCRIPTS = [
        {"key": "scrape", "script": "scraper.py"},
        {"key": "enrich", "script": "enricher.py"},
        {"key": "research", "script": "researcher.py"},
        {"key": "generate", "script": "generator.py"},
        {"key": "review", "script": "reviewer.py"},
        {"key": "blast", "script": "blaster.py"},
        {"key": "track", "script": "reply_tracker.py"},
        {"key": "followup", "script": "followup.py"},
        {"key": "sync", "script": "sheets_sync.py"},
    ]
    return {"status": "success", "data": {"scripts": PIPELINE_SCRIPTS}}