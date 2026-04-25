from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import sqlite3

from oneai_reach.api.dependencies import verify_api_key

router = APIRouter(
    tags=["email-tracking"],
    dependencies=[Depends(verify_api_key)],
)


class EmailEvent(BaseModel):
    id: int
    contact_id: Optional[int] = None
    conversation_id: Optional[int] = None
    lead_id: Optional[str] = None
    wa_number_id: Optional[str] = None
    event_type: str
    email: str
    subject: Optional[str] = None
    message_id: Optional[str] = None
    provider: str = "brevo"
    provider_event_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    link_clicked: Optional[str] = None
    bounce_reason: Optional[str] = None
    timestamp: str
    created_at: str


class EmailEventsResponse(BaseModel):
    events: List[EmailEvent]
    total: int


class EmailStatsResponse(BaseModel):
    contact_id: Optional[int] = None
    conversation_id: Optional[int] = None
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_bounced: int
    open_rate: float
    click_rate: float
    delivery_rate: float
    last_event_at: Optional[str] = None


class EmailTimelineResponse(BaseModel):
    events: List[EmailEvent]
    stats: EmailStatsResponse


def _get_db():
    from oneai_reach.config.settings import get_settings
    settings = get_settings()
    return settings.database.db_file


@router.get("/api/v1/conversations/{conversation_id}/emails", response_model=EmailEventsResponse)
async def get_conversation_emails(
    conversation_id: int,
    event_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> EmailEventsResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    conditions = ["conversation_id = ?"]
    params = [conversation_id]

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    where_clause = " AND ".join(conditions)

    cursor.execute(f"""
        SELECT id, contact_id, conversation_id, lead_id, wa_number_id, event_type,
               email, subject, message_id, provider, provider_event_id, ip_address,
               user_agent, link_clicked, bounce_reason, timestamp, created_at
        FROM email_events
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """, [*params, limit, offset])

    rows = cursor.fetchall()

    cursor.execute(f"SELECT COUNT(*) FROM email_events WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    conn.close()

    events = [
        EmailEvent(
            id=row["id"],
            contact_id=row["contact_id"],
            conversation_id=row["conversation_id"],
            lead_id=row["lead_id"],
            wa_number_id=row["wa_number_id"],
            event_type=row["event_type"],
            email=row["email"],
            subject=row["subject"],
            message_id=row["message_id"],
            provider=row["provider"],
            provider_event_id=row["provider_event_id"],
            ip_address=row["ip_address"],
            user_agent=row["user_agent"],
            link_clicked=row["link_clicked"],
            bounce_reason=row["bounce_reason"],
            timestamp=row["timestamp"],
            created_at=row["created_at"],
        )
        for row in rows
    ]

    return EmailEventsResponse(events=events, total=total)


@router.get("/api/v1/conversations/{conversation_id}/emails/stats", response_model=EmailStatsResponse)
async def get_conversation_email_stats(conversation_id: int) -> EmailStatsResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN event_type = 'sent' THEN 1 END) as total_sent,
            COUNT(CASE WHEN event_type = 'delivered' THEN 1 END) as total_delivered,
            COUNT(CASE WHEN event_type = 'opened' THEN 1 END) as total_opened,
            COUNT(CASE WHEN event_type = 'clicked' THEN 1 END) as total_clicked,
            COUNT(CASE WHEN event_type IN ('bounced', 'hard_bounce', 'soft_bounce') THEN 1 END) as total_bounced,
            MAX(timestamp) as last_event_at
        FROM email_events
        WHERE conversation_id = ?
    """, (conversation_id,))

    row = cursor.fetchone()
    conn.close()

    total_sent = row["total_sent"] or 0
    total_delivered = row["total_delivered"] or 0
    total_opened = row["total_opened"] or 0
    total_clicked = row["total_clicked"] or 0
    total_bounced = row["total_bounced"] or 0

    open_rate = (total_opened / total_delivered * 100) if total_delivered > 0 else 0
    click_rate = (total_clicked / total_delivered * 100) if total_delivered > 0 else 0
    delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0

    return EmailStatsResponse(
        conversation_id=conversation_id,
        total_sent=total_sent,
        total_delivered=total_delivered,
        total_opened=total_opened,
        total_clicked=total_clicked,
        total_bounced=total_bounced,
        open_rate=round(open_rate, 2),
        click_rate=round(click_rate, 2),
        delivery_rate=round(delivery_rate, 2),
        last_event_at=row["last_event_at"],
    )


@router.get("/api/v1/contacts/{contact_id}/emails", response_model=EmailEventsResponse)
async def get_contact_emails(
    contact_id: int,
    event_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> EmailEventsResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    conditions = ["contact_id = ?"]
    params = [contact_id]

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    where_clause = " AND ".join(conditions)

    cursor.execute(f"""
        SELECT id, contact_id, conversation_id, lead_id, wa_number_id, event_type,
               email, subject, message_id, provider, provider_event_id, ip_address,
               user_agent, link_clicked, bounce_reason, timestamp, created_at
        FROM email_events
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """, [*params, limit, offset])

    rows = cursor.fetchall()

    cursor.execute(f"SELECT COUNT(*) FROM email_events WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    conn.close()

    events = [
        EmailEvent(
            id=row["id"],
            contact_id=row["contact_id"],
            conversation_id=row["conversation_id"],
            lead_id=row["lead_id"],
            wa_number_id=row["wa_number_id"],
            event_type=row["event_type"],
            email=row["email"],
            subject=row["subject"],
            message_id=row["message_id"],
            provider=row["provider"],
            provider_event_id=row["provider_event_id"],
            ip_address=row["ip_address"],
            user_agent=row["user_agent"],
            link_clicked=row["link_clicked"],
            bounce_reason=row["bounce_reason"],
            timestamp=row["timestamp"],
            created_at=row["created_at"],
        )
        for row in rows
    ]

    return EmailEventsResponse(events=events, total=total)


@router.get("/api/v1/contacts/{contact_id}/emails/stats", response_model=EmailStatsResponse)
async def get_contact_email_stats(contact_id: int) -> EmailStatsResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN event_type = 'sent' THEN 1 END) as total_sent,
            COUNT(CASE WHEN event_type = 'delivered' THEN 1 END) as total_delivered,
            COUNT(CASE WHEN event_type = 'opened' THEN 1 END) as total_opened,
            COUNT(CASE WHEN event_type = 'clicked' THEN 1 END) as total_clicked,
            COUNT(CASE WHEN event_type IN ('bounced', 'hard_bounce', 'soft_bounce') THEN 1 END) as total_bounced,
            MAX(timestamp) as last_event_at
        FROM email_events
        WHERE contact_id = ?
    """, (contact_id,))

    row = cursor.fetchone()
    conn.close()

    total_sent = row["total_sent"] or 0
    total_delivered = row["total_delivered"] or 0
    total_opened = row["total_opened"] or 0
    total_clicked = row["total_clicked"] or 0
    total_bounced = row["total_bounced"] or 0

    open_rate = (total_opened / total_delivered * 100) if total_delivered > 0 else 0
    click_rate = (total_clicked / total_delivered * 100) if total_delivered > 0 else 0
    delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0

    return EmailStatsResponse(
        contact_id=contact_id,
        total_sent=total_sent,
        total_delivered=total_delivered,
        total_opened=total_opened,
        total_clicked=total_clicked,
        total_bounced=total_bounced,
        open_rate=round(open_rate, 2),
        click_rate=round(click_rate, 2),
        delivery_rate=round(delivery_rate, 2),
        last_event_at=row["last_event_at"],
    )


@router.get("/api/v1/email-tracking/timeline", response_model=EmailTimelineResponse)
async def get_email_timeline(
    contact_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    email: Optional[str] = None,
    days: int = Query(default=30, ge=1, le=365),
) -> EmailTimelineResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    conditions = ["timestamp >= datetime('now', '-{} days')".format(days)]
    params = []

    if contact_id:
        conditions.append("contact_id = ?")
        params.append(contact_id)
    if conversation_id:
        conditions.append("conversation_id = ?")
        params.append(conversation_id)
    if email:
        conditions.append("email = ?")
        params.append(email)

    where_clause = " AND ".join(conditions)

    cursor.execute(f"""
        SELECT id, contact_id, conversation_id, lead_id, wa_number_id, event_type,
               email, subject, message_id, provider, provider_event_id, ip_address,
               user_agent, link_clicked, bounce_reason, timestamp, created_at
        FROM email_events
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT 100
    """, params)

    rows = cursor.fetchall()

    events = [
        EmailEvent(
            id=row["id"],
            contact_id=row["contact_id"],
            conversation_id=row["conversation_id"],
            lead_id=row["lead_id"],
            wa_number_id=row["wa_number_id"],
            event_type=row["event_type"],
            email=row["email"],
            subject=row["subject"],
            message_id=row["message_id"],
            provider=row["provider"],
            provider_event_id=row["provider_event_id"],
            ip_address=row["ip_address"],
            user_agent=row["user_agent"],
            link_clicked=row["link_clicked"],
            bounce_reason=row["bounce_reason"],
            timestamp=row["timestamp"],
            created_at=row["created_at"],
        )
        for row in rows
    ]

    cursor.execute(f"""
        SELECT 
            COUNT(CASE WHEN event_type = 'sent' THEN 1 END) as total_sent,
            COUNT(CASE WHEN event_type = 'delivered' THEN 1 END) as total_delivered,
            COUNT(CASE WHEN event_type = 'opened' THEN 1 END) as total_opened,
            COUNT(CASE WHEN event_type = 'clicked' THEN 1 END) as total_clicked,
            COUNT(CASE WHEN event_type IN ('bounced', 'hard_bounce', 'soft_bounce') THEN 1 END) as total_bounced,
            MAX(timestamp) as last_event_at
        FROM email_events
        WHERE {where_clause}
    """, params)

    stats_row = cursor.fetchone()
    conn.close()

    total_sent = stats_row["total_sent"] or 0
    total_delivered = stats_row["total_delivered"] or 0
    total_opened = stats_row["total_opened"] or 0
    total_clicked = stats_row["total_clicked"] or 0
    total_bounced = stats_row["total_bounced"] or 0

    open_rate = (total_opened / total_delivered * 100) if total_delivered > 0 else 0
    click_rate = (total_clicked / total_delivered * 100) if total_delivered > 0 else 0
    delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0

    stats = EmailStatsResponse(
        contact_id=contact_id,
        conversation_id=conversation_id,
        total_sent=total_sent,
        total_delivered=total_delivered,
        total_opened=total_opened,
        total_clicked=total_clicked,
        total_bounced=total_bounced,
        open_rate=round(open_rate, 2),
        click_rate=round(click_rate, 2),
        delivery_rate=round(delivery_rate, 2),
        last_event_at=stats_row["last_event_at"],
    )

    return EmailTimelineResponse(events=events, stats=stats)
