"""Webhook endpoints for external integrations.

Provides webhook handlers for:
- WAHA (WhatsApp) message and status events
- CAPI (Meta Conversions API) lead tracking events
"""

from oneai_reach.api.webhooks.capi import router as capi_router
from oneai_reach.api.webhooks.waha import router as waha_router

__all__ = ["waha_router", "capi_router"]
