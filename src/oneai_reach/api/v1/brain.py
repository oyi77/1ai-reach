from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from oneai_reach.infrastructure.legacy import brain_client as _brain

router = APIRouter(tags=["brain"])


class BrainAddRequest(BaseModel):
    content: str
    wing: str = _brain.WING_1AI
    room: str = _brain.ROOM_OUTREACH
    hall: str | None = None


class OutcomeRequest(BaseModel):
    lead_name: str
    vertical: str = "Business"
    status: str
    pain_points: str = ""
    review_score: str = ""
    decision_maker: str = ""
    service_type: str = ""


@router.get("/search")
async def search_brain(
    q: str = Query(..., description="Search query"),
    limit: int = Query(5, ge=1, le=50),
    wing: str | None = None,
    room: str | None = None,
    source: str | None = None,
):
    if not _brain.is_online():
        raise HTTPException(502, "Brain hub is offline")
    results = _brain.search(q, limit=limit, wing=wing, room=room, source=source)
    return {"results": results, "count": len(results)}


@router.get("/strategy")
async def get_strategy(
    vertical: str = Query(...),
    location: str = "Jakarta",
    service: str | None = None,
):
    if not _brain.is_online():
        raise HTTPException(502, "Brain hub is offline")
    strategy = _brain.get_strategy(vertical, location, service=service)
    return {"vertical": vertical, "location": location, "strategy": strategy}


@router.get("/recall")
async def recall_brain(
    q: str = Query(..., description="Recall query"),
    limit: int = Query(3, ge=1, le=20),
):
    if not _brain.is_online():
        raise HTTPException(502, "Brain hub is offline")
    results = _brain.recall(q, limit=limit)
    return {"results": results, "count": len(results)}


@router.post("/add")
async def add_to_brain(req: BrainAddRequest):
    if not _brain.is_online():
        raise HTTPException(502, "Brain hub is offline")
    drawer_id = _brain.add(req.content, wing=req.wing, room=req.room, hall=req.hall)
    if not drawer_id:
        raise HTTPException(500, "Failed to store in brain")
    return {"success": True, "drawer_id": drawer_id}


@router.post("/outcome")
async def store_outcome(req: OutcomeRequest):
    if not _brain.is_online():
        raise HTTPException(502, "Brain hub is offline")
    drawer_id = _brain.learn_outcome(
        lead_name=req.lead_name,
        vertical=req.vertical,
        status=req.status,
        pain_points=req.pain_points,
        review_score=req.review_score,
        decision_maker=req.decision_maker,
        service_type=req.service_type,
    )
    if not drawer_id:
        raise HTTPException(500, "Failed to store outcome")
    return {"success": True, "drawer_id": drawer_id}


@router.get("/timeline")
async def brain_timeline(
    service: str | None = None,
    limit: int = Query(20, ge=1, le=100),
):
    if not _brain.is_online():
        raise HTTPException(502, "Brain hub is offline")
    results = _brain.timeline(service=service, limit=limit)
    return {"results": results, "count": len(results)}


@router.get("/stats")
async def brain_stats():
    if not _brain.is_online():
        raise HTTPException(502, "Brain hub is offline")
    stats = _brain.stats()
    return stats or {}


@router.get("/gbrain/search")
async def gbrain_search(
    q: str = Query(..., description="GBrain search query"),
    limit: int = Query(5, ge=1, le=20),
):
    if not _brain.is_online():
        raise HTTPException(502, "Brain hub is offline")
    results = _brain.gbrain_search(q, limit=limit)
    return {"results": results, "count": len(results)}


@router.get("/gbrain/page/{slug}")
async def gbrain_page(slug: str):
    if not _brain.is_online():
        raise HTTPException(502, "Brain hub is offline")
    page = _brain.gbrain_get_page(slug)
    if not page:
        raise HTTPException(404, f"GBrain page '{slug}' not found")
    return page


@router.get("/is-online")
async def brain_health():
    return {"online": _brain.is_online()}