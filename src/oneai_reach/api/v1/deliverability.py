"""Email deliverability API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from oneai_reach.config.settings import Settings, get_settings
from oneai_reach.infrastructure.email.deliverability import (
    get_deliverability_service,
    DomainHealthResult,
    SpamScoreResult,
    WarmupStatus,
)

router = APIRouter(tags=["deliverability"])


class DomainCheckRequest(BaseModel):
    domain: str


class EmailCheckRequest(BaseModel):
    from_email: str
    subject: str
    body: str


class WarmupStartRequest(BaseModel):
    email: str


class WarmupEventRequest(BaseModel):
    email: str
    event: str  # opened, clicked, spam, bounce


@router.get("/health")
async def get_deliverability_health():
    """Get overall deliverability system health."""
    return {
        "status": "healthy",
        "features": {
            "domain_checks": "enabled",
            "spam_scoring": "enabled",
            "warmup_automation": "enabled",
        }
    }


@router.post("/domain/check")
async def check_domain_health(req: DomainCheckRequest):
    """Check domain DNS health (SPF, DKIM, DMARC)."""
    service = get_deliverability_service()
    result = service.check_domain(req.domain)
    
    return {
        "status": "success",
        "data": {
            "domain": result.domain,
            "score": result.score,
            "spf": {"valid": result.spf_valid, "record": result.spf_record},
            "dkim": {"valid": result.dkim_valid, "selectors": result.dkim_selectors},
            "dmarc": {"valid": result.dmarc_valid, "policy": result.dmarc_policy},
            "mx_records": result.mx_records,
            "issues": result.issues,
            "recommendations": result.recommendations,
        }
    }


@router.post("/email/check")
async def check_email_deliverability(req: EmailCheckRequest):
    """Comprehensive pre-send deliverability check."""
    service = get_deliverability_service()
    result = service.check_before_send(req.from_email, req.subject, req.body)
    
    if not result["can_send"]:
        return {
            "status": "warning",
            "message": "Email may have deliverability issues",
            "data": result,
        }
    
    return {
        "status": "success",
        "message": "Email ready to send",
        "data": result,
    }


@router.post("/warmup/start")
async def start_warmup(req: WarmupStartRequest):
    """Start email warm-up process."""
    service = get_deliverability_service()
    status = service.start_warmup(req.email)
    
    return {
        "status": "success",
        "message": f"Warm-up started for {req.email}",
        "data": {
            "email": status.email,
            "day": status.day,
            "daily_limit": status.daily_limit,
            "reputation_score": status.reputation_score,
        }
    }


@router.get("/warmup/status/{email}")
async def get_warmup_status(email: str):
    """Get warm-up status for an email."""
    service = get_deliverability_service()
    status = service.get_status(email)
    
    if not status:
        return {"status": "not_found", "message": "No warm-up in progress"}
    
    return {
        "status": "success",
        "data": {
            "email": status.email,
            "day": status.day,
            "daily_limit": status.daily_limit,
            "sent_today": status.sent_today,
            "total_sent": status.total_sent,
            "reputation_score": status.reputation_score,
            "status": status.status,
            "can_send": service.warmup_service.can_send(email)[0],
        }
    }


@router.post("/warmup/event")
async def record_warmup_event(req: WarmupEventRequest):
    """Record email engagement event."""
    service = get_deliverability_service()
    service.record_event(req.email, req.event)
    
    return {
        "status": "success",
        "message": f"Recorded {req.event} for {req.email}",
    }


@router.get("/overview")
async def get_deliverability_overview(settings: Settings = Depends(get_settings)):
    """Get deliverability overview for all configured domains."""
    service = get_deliverability_service()
    
    # Check main email domain
    from_email = settings.email.smtp_from.split('@')[-1] if '@' in settings.email.smtp_from else "berkahkarya.org"
    domain_health = service.check_domain(from_email)
    
    return {
        "status": "success",
        "data": {
            "primary_domain": from_email,
            "domain_score": domain_health.score,
            "domain_status": "healthy" if domain_health.score >= 80 else "needs_attention" if domain_health.score >= 50 else "critical",
            "spf_configured": domain_health.spf_valid,
            "dkim_configured": domain_health.dkim_valid,
            "dmarc_configured": domain_health.dmarc_valid,
            "dmarc_policy": domain_health.dmarc_policy,
            "issues_count": len(domain_health.issues),
            "recommendations": domain_health.recommendations,
        }
    }
