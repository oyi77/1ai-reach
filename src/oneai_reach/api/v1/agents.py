"""Agent control endpoints for pipeline management and monitoring.

Provides FastAPI endpoints that wrap agent_control.py functions for:
- Starting/stopping background pipeline stages
- Querying funnel state and lead records
- Sending test messages
- Managing WhatsApp sessions
- Inspecting system integrations
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from oneai_reach.api.dependencies import verify_api_key

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(verify_api_key)],
)

# Import agent_control module
_root = Path(__file__).resolve().parent.parent.parent.parent
_scripts_dir = _root / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

try:
    import agent_control
except ImportError as e:
    raise RuntimeError(f"Failed to import agent_control: {e}")


class AgentResponse(BaseModel):
    """Standard agent endpoint response."""

    status: str
    message: str
    data: Optional[Dict[str, Any]] = None


class JobInfo(BaseModel):
    """Job information."""

    job_id: str
    stage: str
    pid: int
    status: str
    log_path: Optional[str] = None


class LeadInfo(BaseModel):
    """Lead information."""

    lead_id: str
    status: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None


class StageStartRequest(BaseModel):
    """Request to start a pipeline stage."""

    args: Optional[List[str]] = None


class StageRunRequest(BaseModel):
    """Request to run a pipeline stage."""

    args: Optional[List[str]] = None
    dry_run: bool = False


class TestEmailRequest(BaseModel):
    """Request to send test email."""

    to: str
    subject: str
    body: str


class TestWhatsAppRequest(BaseModel):
    """Request to send test WhatsApp message."""

    phone: str
    message: str


class SetLeadStatusRequest(BaseModel):
    """Request to set lead status."""

    status: str
    note: Optional[str] = None


class UpdateLeadFieldsRequest(BaseModel):
    """Request to update lead fields."""

    fields: Dict[str, Any]


class CreateWASessionRequest(BaseModel):
    """Request to create WhatsApp session."""

    session_name: str
    phone_number: Optional[str] = None


class AddKBEntryRequest(BaseModel):
    """Request to add knowledge base entry."""

    category: str
    content: str
    tags: Optional[List[str]] = None


@router.get("/config", response_model=AgentResponse)
async def get_config() -> AgentResponse:
    """Get system configuration."""
    try:
        result = agent_control.get_system_config()
        return AgentResponse(
            status="success",
            message="System configuration retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/funnel", response_model=AgentResponse)
async def get_funnel() -> AgentResponse:
    """Get funnel summary."""
    try:
        result = agent_control.get_funnel_summary()
        return AgentResponse(
            status="success",
            message="Funnel summary retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs", response_model=AgentResponse)
async def list_jobs() -> AgentResponse:
    """List all background jobs."""
    try:
        result = agent_control.list_jobs()
        return AgentResponse(
            status="success",
            message="Jobs listed",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", response_model=AgentResponse)
async def get_job(job_id: str, tail_lines: int = 100) -> AgentResponse:
    """Get job details and logs."""
    try:
        result = agent_control.get_job(job_id, tail_lines=tail_lines)
        return AgentResponse(
            status="success",
            message="Job details retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/stop", response_model=AgentResponse)
async def stop_job(job_id: str) -> AgentResponse:
    """Stop a background job."""
    try:
        result = agent_control.stop_job(job_id)
        return AgentResponse(
            status="success",
            message="Job stopped",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stages/{stage}/start", response_model=AgentResponse)
async def start_stage(stage: str, request: StageStartRequest) -> AgentResponse:
    """Start a pipeline stage in background."""
    try:
        result = agent_control.start_background_stage(stage, args=request.args)
        return AgentResponse(
            status="success",
            message=f"Stage '{stage}' started",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stages/{stage}/run", response_model=AgentResponse)
async def run_stage(stage: str, request: StageRunRequest) -> AgentResponse:
    """Run a pipeline stage synchronously."""
    try:
        result = agent_control.run_stage(
            stage, args=request.args, dry_run=request.dry_run
        )
        return AgentResponse(
            status="success",
            message=f"Stage '{stage}' executed",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leads", response_model=AgentResponse)
async def list_leads(status: Optional[str] = None, limit: int = 100) -> AgentResponse:
    """List leads with optional status filter."""
    try:
        result = agent_control.list_leads(status=status, limit=limit)
        return AgentResponse(
            status="success",
            message="Leads listed",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leads/{lead_id}", response_model=AgentResponse)
async def get_lead(lead_id: str) -> AgentResponse:
    """Get lead details."""
    try:
        result = agent_control.get_lead(lead_id)
        return AgentResponse(
            status="success",
            message="Lead details retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/leads/{lead_id}/status", response_model=AgentResponse)
async def set_lead_status(lead_id: str, request: SetLeadStatusRequest) -> AgentResponse:
    """Set lead status."""
    try:
        result = agent_control.set_lead_status(
            lead_id, status=request.status, note=request.note or ""
        )
        return AgentResponse(
            status="success",
            message="Lead status updated",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/leads/{lead_id}/fields", response_model=AgentResponse)
async def update_lead_fields(
    lead_id: str, request: UpdateLeadFieldsRequest
) -> AgentResponse:
    """Update lead fields."""
    try:
        result = agent_control.update_lead_fields(lead_id, fields=request.fields)
        return AgentResponse(
            status="success",
            message="Lead fields updated",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events", response_model=AgentResponse)
async def get_events(limit: int = 100) -> AgentResponse:
    """Get recent system events."""
    try:
        result = agent_control.get_recent_events(limit=limit)
        return AgentResponse(
            status="success",
            message="Recent events retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/integrations", response_model=AgentResponse)
async def get_integrations() -> AgentResponse:
    """Inspect runtime integrations."""
    try:
        result = agent_control.inspect_integrations()
        return AgentResponse(
            status="success",
            message="Integration status retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/email", response_model=AgentResponse)
async def send_test_email(request: TestEmailRequest) -> AgentResponse:
    """Send test email."""
    try:
        result = agent_control.send_test_email(
            to=request.to, subject=request.subject, body=request.body
        )
        return AgentResponse(
            status="success",
            message="Test email sent",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/whatsapp", response_model=AgentResponse)
async def send_test_whatsapp(request: TestWhatsAppRequest) -> AgentResponse:
    """Send test WhatsApp message."""
    try:
        result = agent_control.send_test_whatsapp(
            phone=request.phone, message=request.message
        )
        return AgentResponse(
            status="success",
            message="Test WhatsApp message sent",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wa/sessions", response_model=AgentResponse)
async def list_wa_sessions() -> AgentResponse:
    """List WhatsApp sessions."""
    try:
        result = agent_control.list_wa_sessions()
        return AgentResponse(
            status="success",
            message="WhatsApp sessions listed",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wa/sessions", response_model=AgentResponse)
async def create_wa_session(request: CreateWASessionRequest) -> AgentResponse:
    """Create WhatsApp session."""
    try:
        result = agent_control.create_wa_session(
            session_name=request.session_name,
            phone_number=request.phone_number,
        )
        return AgentResponse(
            status="success",
            message="WhatsApp session created",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wa/sessions/{session_name}", response_model=AgentResponse)
async def get_wa_session_status(session_name: str) -> AgentResponse:
    """Get WhatsApp session status."""
    try:
        result = agent_control.get_wa_session_status(session_name)
        return AgentResponse(
            status="success",
            message="WhatsApp session status retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/wa/sessions/{session_name}", response_model=AgentResponse)
async def delete_wa_session(session_name: str) -> AgentResponse:
    """Delete WhatsApp session."""
    try:
        result = agent_control.delete_wa_session(session_name)
        return AgentResponse(
            status="success",
            message="WhatsApp session deleted",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wa/sessions/{session_name}/qr", response_model=AgentResponse)
async def get_wa_qr_code(session_name: str) -> AgentResponse:
    """Get WhatsApp session QR code."""
    try:
        result = agent_control.get_wa_qr_code(session_name)
        return AgentResponse(
            status="success",
            message="WhatsApp QR code retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kb", response_model=AgentResponse)
async def list_kb_entries(
    wa_number_id: str, category: Optional[str] = None
) -> AgentResponse:
    """List knowledge base entries."""
    try:
        result = agent_control.list_kb_entries(wa_number_id, category=category)
        return AgentResponse(
            status="success",
            message="Knowledge base entries listed",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kb", response_model=AgentResponse)
async def add_kb_entry(request: AddKBEntryRequest) -> AgentResponse:
    """Add knowledge base entry."""
    try:
        result = agent_control.add_kb_entry(
            category=request.category,
            content=request.content,
            tags=request.tags or [],
        )
        return AgentResponse(
            status="success",
            message="Knowledge base entry added",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview", response_model=AgentResponse)
async def preview_decision() -> AgentResponse:
    """Preview autonomous decision."""
    try:
        result = agent_control.preview_autonomous_decision()
        return AgentResponse(
            status="success",
            message="Autonomous decision preview retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshot", response_model=AgentResponse)
async def get_snapshot(limit: int = 100) -> AgentResponse:
    """Get dataframe snapshot."""
    try:
        result = agent_control.load_dataframe_snapshot(limit=limit)
        return AgentResponse(
            status="success",
            message="Dataframe snapshot retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit", response_model=AgentResponse)
async def get_audit(limit: int = 100) -> AgentResponse:
    """Get tool audit log."""
    try:
        result = agent_control.get_tool_audit(limit=limit)
        return AgentResponse(
            status="success",
            message="Tool audit log retrieved",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
