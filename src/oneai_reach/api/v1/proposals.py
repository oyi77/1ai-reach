from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import sqlite3
from datetime import datetime

from oneai_reach.api.dependencies import verify_api_key

router = APIRouter(
    tags=["proposals"],
    dependencies=[Depends(verify_api_key)],
)


class Proposal(BaseModel):
    id: int
    contact_id: int
    conversation_id: Optional[int] = None
    wa_number_id: Optional[str] = None
    lead_id: Optional[str] = None
    title: str
    content: str
    status: str = "draft"
    score: Optional[float] = None
    reviewed: bool = False
    reviewed_at: Optional[str] = None
    review_notes: Optional[str] = None
    sent_at: Optional[str] = None
    accepted_at: Optional[str] = None
    rejected_at: Optional[str] = None
    expires_at: Optional[str] = None
    sent_count: int = 0
    opened_count: int = 0
    clicked_count: int = 0
    value_cents: Optional[int] = None
    currency: str = "IDR"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProposalCreate(BaseModel):
    title: str
    content: str
    conversation_id: Optional[int] = None
    lead_id: Optional[str] = None
    value_cents: Optional[int] = None
    currency: str = "IDR"
    expires_at: Optional[str] = None


class ProposalUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    score: Optional[float] = None
    reviewed: Optional[bool] = None
    review_notes: Optional[str] = None
    value_cents: Optional[int] = None
    expires_at: Optional[str] = None


class ProposalsResponse(BaseModel):
    proposals: List[Proposal]
    total: int


class ProposalResponse(BaseModel):
    proposal: Proposal


def _get_db():
    from oneai_reach.config.settings import get_settings
    settings = get_settings()
    return settings.database.db_file


@router.get("/api/v1/contacts/{contact_id}/proposals", response_model=ProposalsResponse)
async def list_contact_proposals(
    contact_id: int,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> ProposalsResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    conditions = ["contact_id = ?"]
    params = [contact_id]

    if status:
        conditions.append("status = ?")
        params.append(status)

    where_clause = " AND ".join(conditions)

    cursor.execute(f"""
        SELECT id, contact_id, conversation_id, wa_number_id, lead_id, title, content,
               status, score, reviewed, reviewed_at, review_notes, sent_at, accepted_at,
               rejected_at, expires_at, sent_count, opened_count, clicked_count,
               value_cents, currency, created_at, updated_at
        FROM proposals
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, [*params, limit, offset])

    rows = cursor.fetchall()

    cursor.execute(f"SELECT COUNT(*) FROM proposals WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    conn.close()

    proposals = [
        Proposal(
            id=row["id"],
            contact_id=row["contact_id"],
            conversation_id=row["conversation_id"],
            wa_number_id=row["wa_number_id"],
            lead_id=row["lead_id"],
            title=row["title"],
            content=row["content"],
            status=row["status"],
            score=row["score"],
            reviewed=bool(row["reviewed"]),
            reviewed_at=row["reviewed_at"],
            review_notes=row["review_notes"],
            sent_at=row["sent_at"],
            accepted_at=row["accepted_at"],
            rejected_at=row["rejected_at"],
            expires_at=row["expires_at"],
            sent_count=row["sent_count"],
            opened_count=row["opened_count"],
            clicked_count=row["clicked_count"],
            value_cents=row["value_cents"],
            currency=row["currency"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]

    return ProposalsResponse(proposals=proposals, total=total)


@router.post("/api/v1/contacts/{contact_id}/proposals", response_model=ProposalResponse)
async def create_proposal(contact_id: int, proposal: ProposalCreate) -> ProposalResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT wa_number_id FROM contacts WHERE id = ?",
        (contact_id,)
    )
    contact_row = cursor.fetchone()

    if not contact_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Contact not found")

    wa_number_id = contact_row[0]

    cursor.execute("""
        INSERT INTO proposals (contact_id, conversation_id, wa_number_id, lead_id,
                              title, content, status, value_cents, currency, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
    """, (
        contact_id,
        proposal.conversation_id,
        wa_number_id,
        proposal.lead_id,
        proposal.title,
        proposal.content,
        proposal.value_cents,
        proposal.currency,
        proposal.expires_at,
    ))

    proposal_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return ProposalResponse(
        proposal=Proposal(
            id=proposal_id,
            contact_id=contact_id,
            conversation_id=proposal.conversation_id,
            wa_number_id=wa_number_id,
            lead_id=proposal.lead_id,
            title=proposal.title,
            content=proposal.content,
            status="draft",
            value_cents=proposal.value_cents,
            currency=proposal.currency,
            expires_at=proposal.expires_at,
        )
    )


@router.get("/api/v1/proposals/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(proposal_id: int) -> ProposalResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, contact_id, conversation_id, wa_number_id, lead_id, title, content,
               status, score, reviewed, reviewed_at, review_notes, sent_at, accepted_at,
               rejected_at, expires_at, sent_count, opened_count, clicked_count,
               value_cents, currency, created_at, updated_at
        FROM proposals WHERE id = ?
    """, (proposal_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return ProposalResponse(
        proposal=Proposal(
            id=row["id"],
            contact_id=row["contact_id"],
            conversation_id=row["conversation_id"],
            wa_number_id=row["wa_number_id"],
            lead_id=row["lead_id"],
            title=row["title"],
            content=row["content"],
            status=row["status"],
            score=row["score"],
            reviewed=bool(row["reviewed"]),
            reviewed_at=row["reviewed_at"],
            review_notes=row["review_notes"],
            sent_at=row["sent_at"],
            accepted_at=row["accepted_at"],
            rejected_at=row["rejected_at"],
            expires_at=row["expires_at"],
            sent_count=row["sent_count"],
            opened_count=row["opened_count"],
            clicked_count=row["clicked_count"],
            value_cents=row["value_cents"],
            currency=row["currency"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    )


@router.patch("/api/v1/proposals/{proposal_id}", response_model=ProposalResponse)
async def update_proposal(proposal_id: int, update: ProposalUpdate) -> ProposalResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM proposals WHERE id = ?", (proposal_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Proposal not found")

    update_fields = []
    params = []

    if update.title is not None:
        update_fields.append("title = ?")
        params.append(update.title)
    if update.content is not None:
        update_fields.append("content = ?")
        params.append(update.content)
    if update.status is not None:
        update_fields.append("status = ?")
        params.append(update.status)
        if update.status == "sent":
            update_fields.append("sent_at = datetime('now')")
            update_fields.append("sent_count = sent_count + 1")
        elif update.status == "accepted":
            update_fields.append("accepted_at = datetime('now')")
        elif update.status == "rejected":
            update_fields.append("rejected_at = datetime('now')")
    if update.score is not None:
        update_fields.append("score = ?")
        params.append(update.score)
    if update.reviewed is not None:
        update_fields.append("reviewed = ?")
        params.append(1 if update.reviewed else 0)
        if update.reviewed:
            update_fields.append("reviewed_at = datetime('now')")
    if update.review_notes is not None:
        update_fields.append("review_notes = ?")
        params.append(update.review_notes)
    if update.value_cents is not None:
        update_fields.append("value_cents = ?")
        params.append(update.value_cents)
    if update.expires_at is not None:
        update_fields.append("expires_at = ?")
        params.append(update.expires_at)

    if not update_fields:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields.append("updated_at = datetime('now')")
    params.append(proposal_id)

    cursor.execute(
        f"UPDATE proposals SET {', '.join(update_fields)} WHERE id = ?",
        params
    )
    conn.commit()

    cursor.execute("""
        SELECT id, contact_id, conversation_id, wa_number_id, lead_id, title, content,
               status, score, reviewed, reviewed_at, review_notes, sent_at, accepted_at,
               rejected_at, expires_at, sent_count, opened_count, clicked_count,
               value_cents, currency, created_at, updated_at
        FROM proposals WHERE id = ?
    """, (proposal_id,))

    row = cursor.fetchone()
    conn.close()

    return ProposalResponse(
        proposal=Proposal(
            id=row["id"],
            contact_id=row["contact_id"],
            conversation_id=row["conversation_id"],
            wa_number_id=row["wa_number_id"],
            lead_id=row["lead_id"],
            title=row["title"],
            content=row["content"],
            status=row["status"],
            score=row["score"],
            reviewed=bool(row["reviewed"]),
            reviewed_at=row["reviewed_at"],
            review_notes=row["review_notes"],
            sent_at=row["sent_at"],
            accepted_at=row["accepted_at"],
            rejected_at=row["rejected_at"],
            expires_at=row["expires_at"],
            sent_count=row["sent_count"],
            opened_count=row["opened_count"],
            clicked_count=row["clicked_count"],
            value_cents=row["value_cents"],
            currency=row["currency"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    )


@router.delete("/api/v1/proposals/{proposal_id}")
async def delete_proposal(proposal_id: int):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Proposal not found")

    conn.commit()
    conn.close()

    return {"status": "deleted", "proposal_id": proposal_id}


@router.get("/api/v1/conversations/{conversation_id}/proposals", response_model=ProposalsResponse)
async def list_conversation_proposals(
    conversation_id: int,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> ProposalsResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    conditions = ["conversation_id = ?"]
    params = [conversation_id]

    if status:
        conditions.append("status = ?")
        params.append(status)

    where_clause = " AND ".join(conditions)

    cursor.execute(f"""
        SELECT id, contact_id, conversation_id, wa_number_id, lead_id, title, content,
               status, score, reviewed, reviewed_at, review_notes, sent_at, accepted_at,
               rejected_at, expires_at, sent_count, opened_count, clicked_count,
               value_cents, currency, created_at, updated_at
        FROM proposals
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, [*params, limit, offset])

    rows = cursor.fetchall()

    cursor.execute(f"SELECT COUNT(*) FROM proposals WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    conn.close()

    proposals = [
        Proposal(
            id=row["id"],
            contact_id=row["contact_id"],
            conversation_id=row["conversation_id"],
            wa_number_id=row["wa_number_id"],
            lead_id=row["lead_id"],
            title=row["title"],
            content=row["content"],
            status=row["status"],
            score=row["score"],
            reviewed=bool(row["reviewed"]),
            reviewed_at=row["reviewed_at"],
            review_notes=row["review_notes"],
            sent_at=row["sent_at"],
            accepted_at=row["accepted_at"],
            rejected_at=row["rejected_at"],
            expires_at=row["expires_at"],
            sent_count=row["sent_count"],
            opened_count=row["opened_count"],
            clicked_count=row["clicked_count"],
            value_cents=row["value_cents"],
            currency=row["currency"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]

    return ProposalsResponse(proposals=proposals, total=total)
