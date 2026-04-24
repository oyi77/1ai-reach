"""Webhook endpoints for external service integrations.

Handles webhooks from:
- Brevo (email delivery, opens, clicks, bounces)
- WAHA (WhatsApp messages)
- Other external services
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Request, Response, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Load settings
_settings = Settings()


class BrevoWebhookEvent(BaseModel):
    """Brevo webhook event payload."""
    event: str
    email: str
    id: Optional[int] = None
    date: Optional[str] = None
    ts: Optional[int] = None
    message_id: Optional[str] = None
    ts_event: Optional[int] = None
    subject: Optional[str] = None
    tag: Optional[str] = None
    sending_ip: Optional[str] = None
    ts_epoch: Optional[int] = None
    tags: Optional[list] = None
    link: Optional[str] = None
    reason: Optional[str] = None


@router.post("/brevo/events")
async def handle_brevo_webhook(request: Request):
    """Handle Brevo email events webhook.
    
    Events received:
    - delivered: Email successfully delivered to inbox
    - opened: Recipient opened the email
    - clicked: Recipient clicked a link
    - hard_bounce: Email bounced (permanent failure)
    - soft_bounce: Email bounced (temporary failure)
    - spam: Marked as spam
    - unsubscribed: Recipient unsubscribed
    - blocked: Email blocked
    - invalid_email: Invalid email address
    """
    try:
        body = await request.body()
        payload = await request.json()
        
        # Validate webhook signature if configured
        if _settings.email.brevo_webhook_secret:
            signature = request.headers.get("X-Brevo-Signature")
            if not signature:
                logger.warning("Brevo webhook received without signature")
                raise HTTPException(status_code=401, detail="Missing signature")
            
            expected_signature = hmac.new(
                _settings.email.brevo_webhook_secret.encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Brevo webhook signature validation failed")
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        event = BrevoWebhookEvent(**payload)
        logger.info(f"Brevo webhook: {event.event} for {event.email}")
        
        # Import here to avoid circular dependency
        from oneai_reach.infrastructure.database.sqlite_lead_repository import SQLiteLeadRepository
        from pathlib import Path
        
        db_path = Path(_settings.database.db_file)
        repo = SQLiteLeadRepository(str(db_path))
        
        # Find lead by email
        lead = repo.get_by_email(event.email)
        if not lead:
            logger.warning(f"Lead not found for email: {event.email}")
            return {"status": "ignored", "reason": "lead_not_found"}
        
        _log_email_event(
            lead_id=lead.id,
            event_type=f"email_{event.event}",
            details={
                "email": event.email,
                "message_id": event.message_id,
                "timestamp": event.ts or event.ts_event or event.ts_epoch,
                "subject": event.subject,
                "link": event.link,
                "reason": event.reason,
                "tag": event.tag,
            }
        )
        
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        if event.event == "delivered":
            cursor.execute(
                "UPDATE leads SET email_delivered_at = ? WHERE id = ?",
                (timestamp, lead.id)
            )
            logger.info(f"✅ Email delivered to {event.email}")
            
        elif event.event == "opened":
            cursor.execute(
                "UPDATE leads SET email_opened_at = ?, email_open_count = email_open_count + 1 WHERE id = ?",
                (timestamp, lead.id)
            )
            logger.info(f"👁️ Email opened by {event.email}")
            
        elif event.event == "click":
            cursor.execute(
                "UPDATE leads SET email_clicked_at = ?, email_click_count = email_click_count + 1 WHERE id = ?",
                (timestamp, lead.id)
            )
            logger.info(f"🖱️ Link clicked by {event.email}: {event.link}")
            
        elif event.event in ("hard_bounce", "soft_bounce", "blocked", "invalid_email"):
            cursor.execute(
                "UPDATE leads SET status = 'bounced', email_bounce_reason = ? WHERE id = ?",
                (f"{event.event}: {event.reason}", lead.id)
            )
            logger.warning(f"⚠️ Email bounced for {event.email}: {event.reason}")
            
        elif event.event == "spam":
            cursor.execute(
                "UPDATE leads SET status = 'unsubscribed', email_bounce_reason = 'marked_as_spam' WHERE id = ?",
                (lead.id,)
            )
            logger.warning(f"🚫 Email marked as spam by {event.email}")
            
        elif event.event == "unsubscribed":
            cursor.execute(
                "UPDATE leads SET status = 'unsubscribed' WHERE id = ?",
                (lead.id,)
            )
            logger.info(f"🔕 Unsubscribed: {event.email}")
        
        conn.commit()
        conn.close()
        
        return {"status": "success", "event": event.event, "email": event.email}
        
    except Exception as e:
        logger.error(f"Brevo webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/track/open/{lead_id}/{message_id}")
async def track_email_open(lead_id: str, message_id: str):
    """Track email open via 1x1 transparent pixel.
    
    Returns a 1x1 transparent GIF and logs the open event.
    """
    try:
        logger.info(f"📧 Email opened: lead={lead_id}, message={message_id}")
        
        _log_email_event(
            lead_id=lead_id,
            event_type="email_opened_pixel",
            details={"message_id": message_id, "method": "pixel"}
        )
        
        from oneai_reach.infrastructure.database.sqlite_lead_repository import SQLiteLeadRepository
        from pathlib import Path
        
        db_path = Path(_settings.database.db_path)
        
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE leads SET email_opened_at = ?, email_open_count = email_open_count + 1 WHERE id = ?",
            (timestamp, lead_id)
        )
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error tracking email open: {e}")
    
    # Return 1x1 transparent GIF
    gif_data = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
    return Response(content=gif_data, media_type="image/gif")


@router.get("/track/click/{lead_id}/{message_id}")
async def track_email_click(
    lead_id: str,
    message_id: str,
    url: str = Query(..., description="Original URL to redirect to")
):
    """Track email link click and redirect to original URL.
    
    Logs the click event and redirects user to the intended destination.
    """
    try:
        decoded_url = unquote(url)
        logger.info(f"🖱️ Link clicked: lead={lead_id}, message={message_id}, url={decoded_url}")
        
        _log_email_event(
            lead_id=lead_id,
            event_type="email_clicked_link",
            details={"message_id": message_id, "url": decoded_url}
        )
        
        from pathlib import Path
        db_path = Path(_settings.database.db_file)
        
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE leads SET email_clicked_at = ?, email_click_count = email_click_count + 1 WHERE id = ?",
            (timestamp, lead_id)
        )
        conn.commit()
        conn.close()
        
        # Redirect to original URL
        return RedirectResponse(url=decoded_url, status_code=302)
        
    except Exception as e:
        logger.error(f"Error tracking email click: {e}")
        # Still redirect even if tracking fails
        return RedirectResponse(url=unquote(url), status_code=302)


def _log_email_event(lead_id: str, event_type: str, details: Dict[str, Any]):
    """Log email event to event_log table."""
    try:
        from pathlib import Path
        import sqlite3
        
        db_path = Path(_settings.database.db_file)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO event_log (lead_id, event_type, timestamp, details)
            VALUES (?, ?, ?, ?)
            """,
            (
                lead_id,
                event_type,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(details)
            )
        )
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Failed to log email event: {e}")
