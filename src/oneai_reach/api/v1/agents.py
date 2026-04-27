"""Agent control endpoints for pipeline management and monitoring.

Provides FastAPI endpoints that wrap agent_control.py functions for:
- Starting/stopping background pipeline stages
- Querying funnel state and lead records
- Sending test messages
- Managing WhatsApp sessions
- Inspecting system integrations
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from oneai_reach.api.dependencies import verify_api_key, get_db_connection, get_db_path

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(verify_api_key)],
)

agent_control = None
state_manager = None
safe_filename = None
RESEARCH_DIR = None
PROPOSALS_DIR = None
try:
    from oneai_reach.infrastructure.legacy import agent_control
    from oneai_reach.infrastructure.legacy import state_manager
    from oneai_reach.infrastructure.legacy.utils import safe_filename
    from oneai_reach.infrastructure.legacy.config import RESEARCH_DIR, PROPOSALS_DIR
    state_manager.init_db()
except ImportError:
    pass


def load_leads_df():
    """Load leads as pandas DataFrame from SQLite, falling back to CSV."""
    try:
        import pandas as pd
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "leads.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                df = pd.read_sql_query("SELECT * FROM leads", conn)
                return df
            finally:
                conn.close()
        from leads import load_leads
        df = load_leads()
        for col in ["matched_services", "lead_score", "tier", "service_proposed"]:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception as e:
        logger.warning(f"lead stats load failed: {e}")
        return None


def _is_empty_value(val) -> bool:
    """Return True if val is None, NaN, or an empty/sentinel string."""
    if val is None:
        return True
    try:
        import pandas as pd
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    return str(val).strip() in ("", "nan", "None", "<NA>", "NaN")


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


class UpdateModeRequest(BaseModel):
    """Request to update WhatsApp session operational mode."""

    mode: str


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
        
        from oneai_reach.infrastructure.legacy.config import WAHA_URL, WAHA_API_KEY, WAHA_DIRECT_URL, WAHA_DIRECT_API_KEY
        
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


@router.patch("/wa/sessions/{session_name}/mode", response_model=AgentResponse)
async def update_wa_session_mode(
    session_name: str, request: UpdateModeRequest
) -> AgentResponse:
    """Update WhatsApp session operational mode."""
    try:
        result = agent_control.update_wa_session_mode(
            session_name, mode=request.mode
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        return AgentResponse(
            status="success",
            message="WhatsApp session mode updated",
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
            "webhook": ["systemctl", "--user", "restart", "1ai-reach-mcp.service"],
            "dashboard": ["systemctl", "--user", "restart", "1ai-reach-dashboard.service"],
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
            "webhook": ["systemctl", "--user", "stop", "1ai-reach-mcp.service"],
            "dashboard": ["systemctl", "--user", "stop", "1ai-reach-dashboard.service"],
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
    from oneai_reach.infrastructure.legacy import state_manager
    from oneai_reach.infrastructure.legacy.utils import safe_filename
    from oneai_reach.infrastructure.legacy.config import RESEARCH_DIR, PROPOSALS_DIR, LEADS_FILE
    import pandas as pd
    
    try:
        state_manager.init_db()
        
        lead = state_manager.get_lead_by_id(lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail=f"Lead not found: {lead_id}")
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
            except Exception as e:
                logger.warning(f"research file read failed for lead {lead_index}: {e}")
        
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
            except Exception as e:
                logger.warning(f"proposal file parse failed for lead {lead_index}: {e}")
        
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
            pass

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


# ============================================================
# SERVICE DETECTION & SCORING ENDPOINTS
# ============================================================

@router.get("/services/list")
async def list_services():
    """List all available services with match counts from DB."""
    try:
        import json
        df = load_leads_df()
        if df is None or df.empty:
            return AgentResponse(status="ok", message="No leads data", data={"services": []})
        service_counts = {}
        for _, row in df.iterrows():
            ms = row.get("matched_services")
            if _is_empty_value(ms):
                continue
            try:
                services = json.loads(str(ms))
                for s in services:
                    svc_name = s["service"] if isinstance(s, dict) else str(s)
                    service_counts[svc_name] = service_counts.get(svc_name, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        service_list = [{"service": k, "leads_matched": v} for k, v in sorted(service_counts.items(), key=lambda x: -x[1])]
        return AgentResponse(status="ok", message=f"Found {len(service_list)} services", data={"services": service_list})
    except Exception as e:
        return AgentResponse(status="error", message=str(e))


@router.get("/funnel/by-service")
async def funnel_by_service():
    """Funnel breakdown grouped by matched_services."""
    try:
        import json
        from collections import defaultdict
        df = load_leads_df()
        if df is None or df.empty:
            return AgentResponse(status="ok", message="No leads data", data={"breakdown": {}})
        breakdown = defaultdict(lambda: defaultdict(int))
        for _, row in df.iterrows():
            ms = row.get("matched_services")
            status = str(row.get("status", "unknown"))
            service_key = "unmatched"
            if not _is_empty_value(ms):
                try:
                    services = json.loads(str(ms))
                    first = services[0] if services else None
                    service_key = first["service"] if isinstance(first, dict) else str(first) if first else "unmatched"
                except (json.JSONDecodeError, TypeError):
                    pass
            breakdown[service_key][status] += 1
        return AgentResponse(status="ok", message="Funnel by service", data={"breakdown": {k: dict(v) for k, v in breakdown.items()}})
    except Exception as e:
        return AgentResponse(status="error", message=str(e))


@router.get("/leads/by-tier/{tier}")
async def leads_by_tier(tier: str):
    """Get leads filtered by tier (hot/warm/cold/skip)."""
    if tier not in ("hot", "warm", "cold", "skip"):
        return AgentResponse(status="error", message=f"Invalid tier: {tier}. Must be hot/warm/cold/skip")
    try:
        df = load_leads_df()
        if df is None or df.empty:
            return AgentResponse(status="ok", message="No leads data", data={"leads": [], "count": 0})
        filtered = df[df["tier"].astype(str).str.lower() == tier]
        leads_list = filtered.to_dict(orient="records") if not filtered.empty else []
        return AgentResponse(status="ok", message=f"Found {len(leads_list)} {tier} leads", data={"leads": leads_list, "count": len(leads_list)})
    except Exception as e:
        return AgentResponse(status="error", message=str(e))


@router.get("/leads/{lead_id}/services")
async def lead_services(lead_id: str):
    """Get service detection results for a specific lead."""
    try:
        import json
        df = load_leads_df()
        if df is None or df.empty:
            return AgentResponse(status="error", message="No leads data")
        match = df[df["id"].astype(str) == str(lead_id)]
        if match.empty:
            return AgentResponse(status="error", message=f"Lead {lead_id} not found")
        row = match.iloc[0]
        ms = row.get("matched_services")
        services = []
        if not _is_empty_value(ms):
            try:
                services = json.loads(str(ms))
            except (json.JSONDecodeError, TypeError):
                pass
        return AgentResponse(
            status="ok",
            message=f"Services for lead {lead_id}",
            data={
                "lead_id": lead_id,
                "matched_services": services,
                "service_proposed": str(row.get("service_proposed", "")),
                "lead_score": row.get("lead_score"),
                "tier": str(row.get("tier", "")),
            }
        )
    except Exception as e:
        return AgentResponse(status="error", message=str(e))


@router.get("/scoring/stats")
async def scoring_stats():
    """Scoring distribution across tiers."""
    try:
        df = load_leads_df()
        if df is None or df.empty:
            return AgentResponse(status="ok", message="No leads data", data={"distribution": {}, "total": 0})
        tier_counts = df["tier"].astype(str).str.lower().value_counts().to_dict()
        score_col = df["lead_score"].astype(str)
        scored = df[~score_col.isin(["None", "nan", "NaN", "<NA>", ""])]
        try:
            avg_score = float(scored["lead_score"].astype(float).mean()) if not scored.empty else 0.0
        except (ValueError, TypeError):
            avg_score = 0.0
        return AgentResponse(
            status="ok",
            message="Scoring stats",
            data={"distribution": tier_counts, "total": len(df), "scored": len(scored), "avg_score": round(avg_score, 1)},
        )
    except Exception as e:
        return AgentResponse(status="error", message=str(e))


@router.get("/analytics", response_model=AgentResponse)
async def get_analytics() -> AgentResponse:
    """Compute marketing analytics from leads.db: conversion rates, channel perf, lead velocity, campaign ROI."""
    try:
        import json
        import sqlite3
        import pandas as pd
        from datetime import datetime, timedelta, timezone
        from pathlib import Path as _P
        from collections import defaultdict

        db_path = _P(__file__).resolve().parent.parent.parent.parent.parent / "data" / "leads.db"
        if not db_path.exists():
            return AgentResponse(status="ok", message="No leads database", data={})

        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            df = pd.read_sql_query("SELECT * FROM leads", conn)
        finally:
            conn.close()
    
        if df.empty:
            return AgentResponse(status="ok", message="No leads", data={})

        # ── helpers ──────────────────────────────────────────────────────────
        def count(status_val):
            return int((df["status"] == status_val).sum())

        def pct(num, denom):
            return round(num / denom * 100, 1) if denom > 0 else 0.0

        # All leads that have ever progressed past a stage (status in later stages counts too)
        LATER = {
            "new": ["enriched","draft_ready","needs_revision","reviewed","contacted","followed_up","replied","meeting_booked","won","lost","cold"],
            "enriched": ["draft_ready","needs_revision","reviewed","contacted","followed_up","replied","meeting_booked","won","lost"],
            "draft_ready": ["needs_revision","reviewed","contacted","followed_up","replied","meeting_booked","won"],
            "reviewed": ["contacted","followed_up","replied","meeting_booked","won"],
            "contacted": ["followed_up","replied","meeting_booked","won"],
            "replied": ["meeting_booked","won"],
            "meeting_booked": ["won"],
        }

        def at_or_past(stage):
            all_stages = [stage] + LATER.get(stage, [])
            return int(df["status"].isin(all_stages).sum())

        total = len(df)
        n_new = at_or_past("new")
        n_enriched = at_or_past("enriched")
        n_draft = at_or_past("draft_ready")
        n_reviewed = at_or_past("reviewed")
        n_contacted = at_or_past("contacted")
        n_replied = at_or_past("replied")
        n_meeting = at_or_past("meeting_booked")
        n_won = count("won")

        # ── 1. Conversion rates ───────────────────────────────────────────────
        conversion_rates = {
            "new_to_enriched": pct(n_enriched, n_new),
            "enriched_to_draft": pct(n_draft, n_enriched),
            "draft_to_reviewed": pct(n_reviewed, n_draft),
            "reviewed_to_contacted": pct(n_contacted, n_reviewed),
            "contacted_to_replied": pct(n_replied, n_contacted),
            "replied_to_meeting": pct(n_meeting, n_replied),
            "meeting_to_won": pct(n_won, n_meeting),
            "full_funnel": pct(n_won, n_new),
        }

        funnel_counts = {
            "new": n_new,
            "enriched": n_enriched,
            "draft_ready": n_draft,
            "reviewed": n_reviewed,
            "contacted": n_contacted,
            "replied": n_replied,
            "meeting_booked": n_meeting,
            "won": n_won,
            "lost": count("lost"),
            "cold": count("cold"),
            "followed_up": count("followed_up"),
        }

        # ── 2. Channel performance ────────────────────────────────────────────
        # Email
        has_email = df["email"].notna() & (df["email"].astype(str).str.strip() != "")
        contacted_mask = df["status"].isin(["contacted","followed_up","replied","meeting_booked","won"])
        email_sent = int((contacted_mask & has_email).sum())
        email_delivered = int(df["email_delivered_at"].notna().sum())
        email_opened = int(df["email_opened_at"].notna().sum())
        email_clicked = int(df["email_click_count"].fillna(0).astype(float).gt(0).sum()) if "email_click_count" in df.columns else 0
        email_bounced = int(df["email_bounce_reason"].notna().sum()) if "email_bounce_reason" in df.columns else 0

        channel_email = {
            "sent": email_sent,
            "delivered": email_delivered,
            "opened": email_opened,
            "clicked": email_clicked,
            "bounced": email_bounced,
            "delivery_rate": pct(email_delivered, email_sent),
            "open_rate": pct(email_opened, email_delivered if email_delivered else email_sent),
            "click_rate": pct(email_clicked, email_opened if email_opened else email_sent),
            "bounce_rate": pct(email_bounced, email_sent),
        }

        # WhatsApp (has phone + contacted)
        has_phone = df["phone"].notna() & (df["phone"].astype(str).str.strip().str.len() > 5)
        wa_sent = int((contacted_mask & has_phone).sum())
        wa_replied = int((df["status"].isin(["replied","meeting_booked","won"]) & has_phone).sum())
        channel_wa = {
            "sent": wa_sent,
            "replied": wa_replied,
            "reply_rate": pct(wa_replied, wa_sent),
        }

        # ── 3. Lead velocity ─────────────────────────────────────────────────
        now = datetime.now(timezone.utc)
        try:
            df["_created"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
        except Exception as e:
            logger.warning(f"date parse failed for _created: {e}")
            df["_created"] = pd.NaT

        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        leads_this_week = int((df["_created"] >= week_ago).sum())
        leads_this_month = int((df["_created"] >= month_ago).sum())

        # Time to first contact: days from created_at to contacted_at
        avg_days_to_contact = None
        if "contacted_at" in df.columns:
            try:
                df["_contacted"] = pd.to_datetime(df["contacted_at"], utc=True, errors="coerce")
                valid = df[df["_contacted"].notna() & df["_created"].notna()].copy()
                if not valid.empty:
                    delta = (valid["_contacted"] - valid["_created"]).dt.total_seconds() / 86400
                    avg_days_to_contact = round(float(delta.mean()), 1)
            except Exception as e:
                logger.warning(f"velocity calculation failed: {e}")

        velocity = {
            "leads_this_week": leads_this_week,
            "leads_this_month": leads_this_month,
            "avg_days_to_contact": avg_days_to_contact,
        }

        # ── 4. Industry performance ───────────────────────────────────────────
        industry_perf = []
        if "primaryType" in df.columns:
            for industry, grp in df.groupby("primaryType"):
                if not industry or str(industry).strip() in ("", "nan", "None"):
                    continue
                g_total = len(grp)
                g_contacted = int(grp["status"].isin(["contacted","followed_up","replied","meeting_booked","won"]).sum())
                g_replied = int(grp["status"].isin(["replied","meeting_booked","won"]).sum())
                g_converted = int(grp["status"].isin(["meeting_booked","won"]).sum())
                industry_perf.append({
                    "industry": str(industry),
                    "leads": g_total,
                    "contacted": g_contacted,
                    "replied": g_replied,
                    "converted": g_converted,
                    "reply_rate": pct(g_replied, g_contacted),
                    "conversion_rate": pct(g_converted, g_contacted),
                })
            industry_perf.sort(key=lambda x: x["reply_rate"], reverse=True)

        # ── 5. Tier distribution + reply rate ────────────────────────────────
        tier_stats = {}
        if "tier" in df.columns:
            for tier in ["hot", "warm", "cold", "skip"]:
                mask = df["tier"].astype(str).str.lower() == tier
                t_total = int(mask.sum())
                t_replied = int((mask & df["status"].isin(["replied","meeting_booked","won"])).sum())
                tier_stats[tier] = {
                    "count": t_total,
                    "replied": t_replied,
                    "reply_rate": pct(t_replied, t_total),
                }

        # ── 6. Lead score histogram ───────────────────────────────────────────
        score_hist = {"0-3": 0, "3-5": 0, "5-7": 0, "7-10": 0}
        if "lead_score" in df.columns:
            scores = pd.to_numeric(df["lead_score"], errors="coerce").dropna()
            score_hist["0-3"] = int((scores < 3).sum())
            score_hist["3-5"] = int(((scores >= 3) & (scores < 5)).sum())
            score_hist["5-7"] = int(((scores >= 5) & (scores < 7)).sum())
            score_hist["7-10"] = int((scores >= 7).sum())

        # Avg score
        avg_score = 0.0
        if "lead_score" in df.columns:
            numeric_scores = pd.to_numeric(df["lead_score"], errors="coerce").dropna()
            if not numeric_scores.empty:
                avg_score = round(float(numeric_scores.mean()), 1)

        # ── 7. Service performance ────────────────────────────────────────────
        service_perf: dict = {}
        if "matched_services" in df.columns:
            for _, row in df.iterrows():
                ms = row.get("matched_services")
                if not ms or str(ms).strip() in ("", "nan", "None"):
                    continue
                try:
                    services_list = json.loads(str(ms))
                    for s in services_list:
                        svc = s["service"] if isinstance(s, dict) else str(s)
                        if svc not in service_perf:
                            service_perf[svc] = {"total": 0, "contacted": 0, "replied": 0}
                        service_perf[svc]["total"] += 1
                        if row.get("status") in ["contacted","followed_up","replied","meeting_booked","won"]:
                            service_perf[svc]["contacted"] += 1
                        if row.get("status") in ["replied","meeting_booked","won"]:
                            service_perf[svc]["replied"] += 1
                except (json.JSONDecodeError, TypeError):
                    pass
            # Compute rates
            for svc, d in service_perf.items():
                d["reply_rate"] = pct(d["replied"], d["contacted"])

            service_perf_list = [{"service": k, **v} for k, v in service_perf.items()]
            service_perf_list.sort(key=lambda x: x["reply_rate"], reverse=True)
        else:
            service_perf_list = []

        # ── KPI summary ───────────────────────────────────────────────────────
        active_stages = ["enriched","draft_ready","needs_revision","reviewed","contacted","followed_up","replied","meeting_booked"]
        pipeline_active = int(df["status"].isin(active_stages).sum())

        kpis = {
            "total_leads": total,
            "full_funnel_conversion": conversion_rates["full_funnel"],
            "reply_rate": conversion_rates["contacted_to_replied"],
            "avg_lead_score": avg_score,
            "leads_this_week": leads_this_week,
            "pipeline_active": pipeline_active,
        }

        return AgentResponse(
            status="success",
            message="Analytics computed",
            data={
                "kpis": kpis,
                "conversion_rates": conversion_rates,
                "funnel_counts": funnel_counts,
                "channel_email": channel_email,
                "channel_wa": channel_wa,
                "velocity": velocity,
                "industry_performance": industry_perf,
                "tier_stats": tier_stats,
                "score_histogram": score_hist,
                "service_performance": service_perf_list,
            },
        )
    except Exception as e:
        import traceback
        return AgentResponse(status="error", message=f"Analytics error: {str(e)}\n{traceback.format_exc()}", data={})


@router.get("/experiments/status")
async def experiments_status():
    """A/B test stats across all services."""
    try:
        import json as _json
        from pathlib import Path as _Path
        from config import DATA_DIR as _DATA_DIR
        experiments_dir = _Path(_DATA_DIR) / "experiments"
        if not experiments_dir.exists():
            return AgentResponse(status="ok", message="No experiments yet", data={"experiments": {}})
        experiments = {}
        for service_dir in experiments_dir.iterdir():
            if not service_dir.is_dir():
                continue
            service_name = service_dir.name
            experiments[service_name] = {}
            for stats_file in service_dir.glob("*.json"):
                variant_type = stats_file.stem
                with open(stats_file) as f:
                    experiments[service_name][variant_type] = _json.load(f)
        return AgentResponse(
            status="ok",
            message=f"Found {len(experiments)} services with experiments",
            data={"experiments": experiments}
        )
    except Exception as e:
        return AgentResponse(status="error", message=str(e))
