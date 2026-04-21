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

_root = Path(__file__).resolve().parent.parent.parent.parent.parent
_scripts_dir = _root / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

agent_control = None
state_manager = None
safe_filename = None
RESEARCH_DIR = None
PROPOSALS_DIR = None
try:
    import agent_control
    import state_manager
    from utils import safe_filename
    from config import RESEARCH_DIR, PROPOSALS_DIR
    state_manager.init_db()
except ImportError:
    pass


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


class UpdatePersonaRequest(BaseModel):
    """Request to update WhatsApp session persona."""

    persona: str


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
        if not agent_control:
            return AgentResponse(
                status="error",
                message="Agent control module not available",
                data={"stages": {}, "total": 0},
            )
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


@router.get("/wa/sessions/status", response_model=AgentResponse)
async def get_wa_sessions_status() -> AgentResponse:
    """Get live WAHA session status from API.
    
    Fetches current session status from WAHA API and returns array of sessions
    with name, status, and phone number.
    """
    try:
        import requests
        
        sys.path.insert(0, str(_scripts_dir))
        from config import WAHA_URL, WAHA_API_KEY, WAHA_DIRECT_URL, WAHA_DIRECT_API_KEY
        
        sessions = []
        
        targets = [
            ("WAHA", WAHA_URL, WAHA_API_KEY),
            ("WAHA_DIRECT", WAHA_DIRECT_URL, WAHA_DIRECT_API_KEY),
        ]
        
        for target_name, base_url, api_key in targets:
            url = str(base_url or "").rstrip("/")
            key = str(api_key or "")
            
            if not url or not key:
                continue
            
            try:
                headers = {"X-Api-Key": key}
                response = requests.get(
                    f"{url}/api/sessions",
                    params={"all": "true"},
                    headers=headers,
                    timeout=10,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        for item in data:
                            session_name = str(item.get("name") or "").strip()
                            status = str(item.get("status") or "").upper()
                            phone = str(item.get("phone") or "").strip()
                            
                            if status not in ["WORKING", "SCAN_QR_CODE", "FAILED", "STOPPED"]:
                                status = "UNKNOWN"
                            
                            if session_name:
                                sessions.append({
                                    "name": session_name,
                                    "status": status,
                                    "phone": phone,
                                })
            except Exception as e:
                print(f"Error fetching from {target_name}: {e}", file=sys.stderr)
                continue
        
        return AgentResponse(
            status="success",
            message="WAHA session status retrieved",
            data={"sessions": sessions},
        )
    except Exception as e:
        return AgentResponse(
            status="success",
            message="WAHA session status retrieved (with errors)",
            data={"sessions": []},
        )


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


@router.patch("/wa/sessions/{session_name}/persona", response_model=AgentResponse)
async def update_wa_session_persona(
    session_name: str, request: UpdatePersonaRequest
) -> AgentResponse:
    """Update WhatsApp session persona."""
    try:
        result = agent_control.update_wa_session_persona(
            session_name, persona=request.persona
        )
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("error"))
        return AgentResponse(
            status="success",
            message="WhatsApp session persona updated",
            data=result,
        )
    except HTTPException:
        raise
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


class AutonomousStartRequest(BaseModel):
    """Request to start autonomous loop."""

    dry_run: bool = False
    run_once: bool = False


@router.post("/autonomous/start", response_model=AgentResponse)
async def start_autonomous(request: AutonomousStartRequest) -> AgentResponse:
    """Start autonomous loop with optional dry_run/run_once modes."""
    try:
        args = []
        if request.dry_run:
            args.append("--dry-run")
        if request.run_once:
            args.append("--run-once")
        
        result = agent_control.start_background_stage("autonomous_loop", args=args)
        return AgentResponse(
            status="success",
            message="Autonomous loop started",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autonomous/stop", response_model=AgentResponse)
async def stop_autonomous() -> AgentResponse:
    """Stop autonomous loop."""
    try:
        # Find running autonomous_loop job
        jobs_result = agent_control.list_jobs()
        autonomous_job = None
        for job in jobs_result.get("items", []):
            if job.get("stage") == "autonomous_loop" and job.get("running"):
                autonomous_job = job
                break
        
        if not autonomous_job:
            return AgentResponse(
                status="success",
                message="No autonomous loop running",
                data={"was_running": False},
            )
        
        result = agent_control.stop_job(autonomous_job["job_id"])
        return AgentResponse(
            status="success",
            message="Autonomous loop stopped",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/services/{key}/restart", response_model=AgentResponse)
async def restart_service(key: str) -> AgentResponse:
    """Restart a service (webhook, dashboard, etc)."""
    try:
        import subprocess
        
        service_commands = {
            "webhook": ["sudo", "systemctl", "restart", "1ai-reach-mcp"],
            "dashboard": ["sudo", "systemctl", "restart", "1ai-reach-dashboard"],
        }
        
        if key not in service_commands:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown service: {key}. Valid services: {list(service_commands.keys())}",
            )
        
        cmd = service_commands[key]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to restart {key}: {proc.stderr}",
            )
        
        return AgentResponse(
            status="success",
            message=f"Service '{key}' restarted",
            data={"service": key, "command": " ".join(cmd)},
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail=f"Restart command timed out for {key}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/services/{key}/stop", response_model=AgentResponse)
async def stop_service(key: str) -> AgentResponse:
    """Stop a service."""
    try:
        import subprocess
        
        service_commands = {
            "webhook": ["sudo", "systemctl", "stop", "1ai-reach-mcp"],
            "dashboard": ["sudo", "systemctl", "stop", "1ai-reach-dashboard"],
        }
        
        if key not in service_commands:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown service: {key}. Valid services: {list(service_commands.keys())}",
            )
        
        cmd = service_commands[key]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to stop {key}: {proc.stderr}",
            )
        
        return AgentResponse(
            status="success",
            message=f"Service '{key}' stopped",
            data={"service": key, "command": " ".join(cmd)},
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail=f"Stop command timed out for {key}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leads/{lead_id}/timeline", response_model=AgentResponse)
async def get_lead_timeline(lead_id: str) -> AgentResponse:
    """Get complete timeline for a lead including research, proposal, and conversation messages."""
    try:
        import sys
        from pathlib import Path as P
        import logging
        
        logger = logging.getLogger(__name__)
        
        _root = P(__file__).resolve().parent.parent.parent.parent.parent
        _scripts_dir = _root / "scripts"
        if str(_scripts_dir) not in sys.path:
            sys.path.insert(0, str(_scripts_dir))
        
        import state_manager
        from utils import safe_filename
        from config import RESEARCH_DIR, PROPOSALS_DIR, LEADS_FILE, DB_FILE
        import pandas as pd
        
        logger.info(f"Timeline request for lead_id: {lead_id}")
        logger.info(f"DB_FILE: {DB_FILE}, exists: {DB_FILE.exists()}")
        
        state_manager.init_db()
        
        lead = state_manager.get_lead_by_id(lead_id)
        logger.info(f"Lead query result: {lead is not None}")
        if not lead:
            raise HTTPException(status_code=404, detail=f"Lead not found in database: {lead_id}")
        
        df = pd.read_csv(str(LEADS_FILE))
        matching_rows = df[df['id'] == lead_id]
        if len(matching_rows) == 0:
            raise HTTPException(status_code=404, detail=f"Lead not found in CSV: {lead_id}")
        lead_index = matching_rows.index[0]
        
        research_text = None
        sanitized_name = safe_filename(lead.get("displayName", ""))
        research_file = P(RESEARCH_DIR) / f"{lead_index}_{sanitized_name}.txt"
        if research_file.exists():
            try:
                research_text = research_file.read_text(encoding="utf-8")
            except Exception:
                pass
        
        proposal_data = {"email": None, "whatsapp": None}
        proposal_file = P(PROPOSALS_DIR) / f"{lead_index}_{sanitized_name}.txt"
        if proposal_file.exists():
            try:
                proposal_content = proposal_file.read_text(encoding="utf-8")
                parts = proposal_content.split("---PROPOSAL---")
                if len(parts) > 1:
                    email_and_wa = parts[1].split("---WHATSAPP---")
                    proposal_data["email"] = email_and_wa[0].strip() if email_and_wa else None
                    proposal_data["whatsapp"] = email_and_wa[1].strip() if len(email_and_wa) > 1 else None
            except Exception:
                pass
        
        messages = []
        conn = state_manager._connect()
        try:
            rows = conn.execute(
                """
                SELECT cm.id, cm.direction, cm.message_text, cm.message_type, cm.waha_message_id, cm.timestamp
                FROM conversation_messages cm
                JOIN conversations c ON cm.conversation_id = c.id
                WHERE c.lead_id = ?
                ORDER BY cm.timestamp ASC
                """,
                (lead_id,)
            ).fetchall()
            messages = [dict(row) for row in rows]
        finally:
            conn.close()
        
        return AgentResponse(
            status="success",
            message="Lead timeline retrieved",
            data={
                "lead": lead,
                "research": research_text,
                "proposal": proposal_data,
                "messages": messages,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
