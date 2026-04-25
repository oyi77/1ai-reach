"""Quick reply templates CRUD endpoints."""

import logging
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from oneai_reach.api.dependencies import verify_api_key
from oneai_reach.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/templates",
    tags=["templates"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("")
async def api_list_templates(wa_number_id: str | None = None):
    """List all quick reply templates, optionally filtered by WA number."""
    settings = get_settings()
    db_path = settings.database.db_file

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if wa_number_id:
            rows = conn.execute(
                "SELECT * FROM quick_reply_templates WHERE wa_number_id = ? OR wa_number_id IS NULL ORDER BY category, name",
                (wa_number_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM quick_reply_templates ORDER BY category, name"
            ).fetchall()
        return {"status": "success", "data": {"templates": [dict(r) for r in rows]}}
    finally:
        conn.close()


@router.post("")
async def api_create_template(request: Request):
    """Create a new quick reply template."""
    data = await request.json()
    name = data.get("name")
    content = data.get("content")
    if not name or not content:
        raise HTTPException(status_code=400, detail="name and content required")

    category = data.get("category", "general")
    wa_number_id = data.get("wa_number_id")

    settings = get_settings()
    db_path = settings.database.db_file

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "INSERT INTO quick_reply_templates (wa_number_id, name, content, category) VALUES (?, ?, ?, ?)",
            (wa_number_id, name, content, category),
        )
        conn.commit()
        template_id = cursor.lastrowid
        return {"status": "success", "data": {"id": template_id, "name": name, "content": content, "category": category}}
    except Exception as e:
        conn.rollback()
        logger.error(f"create template failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/{template_id}")
async def api_update_template(template_id: int, request: Request):
    """Update a quick reply template."""
    data = await request.json()
    settings = get_settings()
    db_path = settings.database.db_file

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute("SELECT id FROM quick_reply_templates WHERE id = ?", (template_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found")

        updates = []
        values = []
        for field in ("name", "content", "category", "wa_number_id"):
            if field in data:
                updates.append(f"{field} = ?")
                values.append(data[field])

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = datetime('now')")
        values.append(template_id)
        conn.execute(f"UPDATE quick_reply_templates SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()

        row = conn.execute("SELECT * FROM quick_reply_templates WHERE id = ?", (template_id,)).fetchone()
        return {"status": "success", "data": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"update template failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.delete("/{template_id}")
async def api_delete_template(template_id: int):
    """Delete a quick reply template."""
    settings = get_settings()
    db_path = settings.database.db_file

    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute("SELECT id FROM quick_reply_templates WHERE id = ?", (template_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found")

        conn.execute("DELETE FROM quick_reply_templates WHERE id = ?", (template_id,))
        conn.commit()
        return {"status": "success", "data": {"deleted": template_id}}
    finally:
        conn.close()