"""CAPI webhook endpoints for Meta Conversions API lead tracking."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from oneai_reach.infrastructure.legacy import capi_tracker

router = APIRouter(prefix="/api/v1/webhooks/capi", tags=["webhooks"])


class CAPILeadPayload(BaseModel):
    phone: str = Field(..., description="Contact phone number")
    event_type: Optional[str] = Field(
        "lead", description="Event type (lead/purchase/atc)"
    )


class CAPIWebhookResponse(BaseModel):
    status: str
    tracked: bool
    event_type: str


@router.post("/lead", response_model=CAPIWebhookResponse)
async def handle_capi_lead(payload: CAPILeadPayload) -> CAPIWebhookResponse:
    """Handle CAPI lead tracking webhook.

    Tracks lead events to Meta Conversions API for attribution and optimization.
    """
    try:
        phone = payload.phone
        event_type = payload.event_type or "lead"

        if event_type == "lead":
            capi_tracker.track_lead(phone)
        elif event_type == "purchase":
            capi_tracker.track_purchase(phone)
        elif event_type == "atc":
            capi_tracker.track_atc(phone)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event_type: {event_type}. Must be lead/purchase/atc",
            )

        return CAPIWebhookResponse(
            status="ok",
            tracked=True,
            event_type=event_type,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CAPI WEBHOOK ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))
