"""Knowledge base API endpoints."""

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

_SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import state_manager
import kb_manager

router = APIRouter(tags=["kb"])


@router.get("/{wa_number_id}")
async def api_kb_list(wa_number_id: str, category: Optional[str] = None):
    entries = state_manager.get_kb_entries(wa_number_id, category=category)
    return {"status": "success", "data": {"entries": entries, "count": len(entries)}}


@router.post("/{wa_number_id}")
async def api_kb_add(wa_number_id: str, request: Request):
    data = await request.json()
    if not data.get("question") or not data.get("answer"):
        raise HTTPException(status_code=400, detail="question and answer required")
    entry_id = kb_manager.add_entry(
        wa_number_id=wa_number_id,
        question=data["question"],
        answer=data["answer"],
        category=data.get("category", "faq"),
        tags=data.get("tags", ""),
    )
    return JSONResponse(status_code=201, content={"status": "success", "data": {"ok": True, "entry_id": entry_id}})


@router.patch("/entry/{entry_id}")
async def api_kb_update(entry_id: int, request: Request):
    data = await request.json()
    ok = kb_manager.update_entry(entry_id, **data)
    if not ok:
        raise HTTPException(status_code=404, detail="not_found")
    return {"status": "success", "data": {"ok": True}}


@router.delete("/entry/{entry_id}")
async def api_kb_delete(entry_id: int):
    state_manager.delete_kb_entry(entry_id)
    return {"status": "success", "data": {"ok": True}}


@router.post("/{wa_number_id}/import")
async def api_kb_import(wa_number_id: str, request: Request):
    data = await request.json()
    entries = data.get("entries", [])
    count = kb_manager.import_entries(wa_number_id, entries)
    return {"status": "success", "data": {"ok": True, "imported": count}}


@router.get("/{wa_number_id}/export")
async def api_kb_export(wa_number_id: str):
    entries = kb_manager.export_entries(wa_number_id)
    return {"status": "success", "data": {"entries": entries, "count": len(entries)}}