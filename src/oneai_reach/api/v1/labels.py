from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import sqlite3

from oneai_reach.api.dependencies import verify_api_key
from oneai_reach.infrastructure.external.waha_client import WAHAClient

router = APIRouter(
    tags=["waha-labels"],
    dependencies=[Depends(verify_api_key)],
)


class WahaLabel(BaseModel):
    id: int
    wa_number_id: str
    waha_label_id: str
    name: str
    color: Optional[str] = None
    is_predefined: bool = False
    is_active: bool = True
    created_at: str
    updated_at: str


class WahaLabelCreate(BaseModel):
    name: str
    color: Optional[str] = None


class WahaLabelUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


class WahaLabelsResponse(BaseModel):
    labels: List[WahaLabel]


class WahaLabelResponse(BaseModel):
    label: WahaLabel


class LabelAssignment(BaseModel):
    conversation_id: int
    label_id: int
    assigned_at: str
    assigned_by: Optional[str] = None


class LabelAssignmentsResponse(BaseModel):
    assignments: List[LabelAssignment]


def _get_db():
    from oneai_reach.config.settings import get_settings
    settings = get_settings()
    return settings.database.db_file


def _get_waha_client(wa_number_id: str):
    from oneai_reach.config.settings import get_settings
    settings = get_settings()
    return WAHAClient(
        base_url=settings.waha_api_url,
        api_key=settings.waha_api_key,
    )


@router.get("/{wa_number_id}/labels", response_model=WahaLabelsResponse)
async def list_waha_labels(wa_number_id: str) -> WahaLabelsResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, wa_number_id, waha_label_id, name, color, is_predefined, is_active, created_at, updated_at
        FROM waha_labels
        WHERE wa_number_id = ? AND is_active = 1
        ORDER BY name
    """, (wa_number_id,))

    rows = cursor.fetchall()
    conn.close()

    labels = [
        WahaLabel(
            id=row["id"],
            wa_number_id=row["wa_number_id"],
            waha_label_id=row["waha_label_id"],
            name=row["name"],
            color=row["color"],
            is_predefined=bool(row["is_predefined"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]

    return WahaLabelsResponse(labels=labels)


@router.post("/{wa_number_id}/labels", response_model=WahaLabelResponse)
async def create_waha_label(wa_number_id: str, label: WahaLabelCreate) -> WahaLabelResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM wa_numbers WHERE id = ?",
        (wa_number_id,)
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="WA number not found")

    import uuid
    waha_label_id = str(uuid.uuid4())[:8]

    cursor.execute("""
        INSERT INTO waha_labels (wa_number_id, waha_label_id, name, color, is_predefined, is_active)
        VALUES (?, ?, ?, ?, 0, 1)
    """, (wa_number_id, waha_label_id, label.name, label.color))

    label_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return WahaLabelResponse(
        label=WahaLabel(
            id=label_id,
            wa_number_id=wa_number_id,
            waha_label_id=waha_label_id,
            name=label.name,
            color=label.color,
            is_predefined=False,
            is_active=True,
            created_at="",
            updated_at="",
        )
    )


@router.patch("/{wa_number_id}/labels/{label_id}", response_model=WahaLabelResponse)
async def update_waha_label(
    wa_number_id: str,
    label_id: int,
    update: WahaLabelUpdate
) -> WahaLabelResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM waha_labels WHERE id = ? AND wa_number_id = ?",
        (label_id, wa_number_id)
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Label not found")

    update_fields = []
    params = []

    if update.name is not None:
        update_fields.append("name = ?")
        params.append(update.name)
    if update.color is not None:
        update_fields.append("color = ?")
        params.append(update.color)
    if update.is_active is not None:
        update_fields.append("is_active = ?")
        params.append(1 if update.is_active else 0)

    if not update_fields:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields.append("updated_at = datetime('now')")
    params.append(label_id)

    cursor.execute(
        f"UPDATE waha_labels SET {', '.join(update_fields)} WHERE id = ?",
        params
    )
    conn.commit()

    cursor.execute("""
        SELECT id, wa_number_id, waha_label_id, name, color, is_predefined, is_active, created_at, updated_at
        FROM waha_labels WHERE id = ?
    """, (label_id,))

    row = cursor.fetchone()
    conn.close()

    return WahaLabelResponse(
        label=WahaLabel(
            id=row["id"],
            wa_number_id=row["wa_number_id"],
            waha_label_id=row["waha_label_id"],
            name=row["name"],
            color=row["color"],
            is_predefined=bool(row["is_predefined"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    )


@router.delete("/{wa_number_id}/labels/{label_id}")
async def delete_waha_label(wa_number_id: str, label_id: int):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM waha_label_assignments WHERE waha_label_id = ?",
        (label_id,)
    )

    cursor.execute(
        "DELETE FROM waha_labels WHERE id = ? AND wa_number_id = ?",
        (label_id, wa_number_id)
    )

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Label not found")

    conn.commit()
    conn.close()

    return {"status": "deleted", "label_id": label_id}


@router.get("/api/v1/conversations/{conversation_id}/labels", response_model=WahaLabelsResponse)
async def get_conversation_labels(conversation_id: int) -> WahaLabelsResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT l.id, l.wa_number_id, l.waha_label_id, l.name, l.color, l.is_predefined, l.is_active, l.created_at, l.updated_at
        FROM waha_labels l
        JOIN waha_label_assignments la ON l.id = la.waha_label_id
        WHERE la.conversation_id = ? AND l.is_active = 1
        ORDER BY l.name
    """, (conversation_id,))

    rows = cursor.fetchall()
    conn.close()

    labels = [
        WahaLabel(
            id=row["id"],
            wa_number_id=row["wa_number_id"],
            waha_label_id=row["waha_label_id"],
            name=row["name"],
            color=row["color"],
            is_predefined=bool(row["is_predefined"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]

    return WahaLabelsResponse(labels=labels)


@router.post("/api/v1/conversations/{conversation_id}/labels/{label_id}")
async def assign_label_to_conversation(
    conversation_id: int,
    label_id: int,
    assigned_by: Optional[str] = None
):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM conversations WHERE id = ?",
        (conversation_id,)
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Conversation not found")

    cursor.execute(
        "SELECT id FROM waha_labels WHERE id = ?",
        (label_id,)
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Label not found")

    try:
        cursor.execute("""
            INSERT INTO waha_label_assignments (conversation_id, waha_label_id, assigned_by)
            VALUES (?, ?, ?)
        """, (conversation_id, label_id, assigned_by))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Label already assigned to this conversation")

    conn.close()

    return {"status": "assigned", "conversation_id": conversation_id, "label_id": label_id}


@router.delete("/api/v1/conversations/{conversation_id}/labels/{label_id}")
async def remove_label_from_conversation(conversation_id: int, label_id: int):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM waha_label_assignments WHERE conversation_id = ? AND waha_label_id = ?",
        (conversation_id, label_id)
    )

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Label assignment not found")

    conn.commit()
    conn.close()

    return {"status": "removed", "conversation_id": conversation_id, "label_id": label_id}


@router.get("/api/v1/labels/filter/conversations")
async def get_conversations_by_labels(
    label_ids: str,
    wa_number_id: Optional[str] = None,
) -> dict:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    label_id_list = [int(x.strip()) for x in label_ids.split(",") if x.strip().isdigit()]

    if not label_id_list:
        conn.close()
        raise HTTPException(status_code=400, detail="No valid label IDs provided")

    placeholders = ",".join(["?"] * len(label_id_list))

    query = f"""
        SELECT c.id, c.contact_phone, c.contact_name, c.status, c.last_message_at
        FROM conversations c
        JOIN waha_label_assignments la ON c.id = la.conversation_id
        WHERE la.waha_label_id IN ({placeholders})
    """
    params = label_id_list

    if wa_number_id:
        query += " AND c.wa_number_id = ?"
        params.append(wa_number_id)

    query += " GROUP BY c.id ORDER BY c.last_message_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    conversations = [
        {
            "id": row["id"],
            "contact_phone": row["contact_phone"],
            "contact_name": row["contact_name"],
            "status": row["status"],
            "last_message_at": row["last_message_at"],
        }
        for row in rows
    ]

    return {"conversations": conversations, "total": len(conversations)}
