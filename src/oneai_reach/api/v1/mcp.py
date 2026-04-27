"""MCP (Model Context Protocol) endpoints for 1ai-reach control plane.

Provides JSON-RPC 2.0 compatible endpoints for AI agents to inspect and control
the 1ai-reach backend safely. Migrated from mcp_server.py to unified FastAPI app.
"""

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from oneai_reach.api.dependencies import verify_api_key
from oneai_reach.infrastructure.legacy import agent_control as control

router = APIRouter(
    prefix="/api/v1/mcp",
    tags=["mcp"],
    dependencies=[Depends(verify_api_key)],
)


# ============================================================================
# Pydantic Models
# ============================================================================


class MCPRequest(BaseModel):
    """JSON-RPC 2.0 request model."""

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(..., description="MCP method name")
    params: Optional[Dict[str, Any]] = Field(
        default=None, description="Method parameters"
    )
    id: Union[int, str] = Field(..., description="Request ID")


class MCPResponse(BaseModel):
    """JSON-RPC 2.0 response model."""

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Method result")
    error: Optional[Dict[str, Any]] = Field(default=None, description="Error object")
    id: Union[int, str] = Field(..., description="Request ID")


class MCPError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Optional[Any] = Field(default=None, description="Additional error data")


# ============================================================================
# MCP Method Handlers
# ============================================================================


def handle_get_system_config(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Return core runtime config relevant to agent control."""
    return control.get_system_config()


def handle_get_funnel_summary(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Return funnel counts across all stages."""
    return control.get_funnel_summary()


def handle_list_leads(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """List current leads from SQLite state."""
    params = params or {}
    status = params.get("status")
    limit = params.get("limit", 100)
    return control.list_leads(status=status, limit=limit)


def handle_get_lead(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get one lead plus recent event log entries."""
    params = params or {}
    lead_id = params.get("lead_id")
    if not lead_id:
        raise ValueError("lead_id is required")
    return control.get_lead(lead_id)


def handle_get_recent_events(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Return recent event log entries from the pipeline database."""
    params = params or {}
    limit = params.get("limit", 100)
    return control.get_recent_events(limit=limit)


def handle_get_tool_audit(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Return control-plane tool audit history."""
    params = params or {}
    limit = params.get("limit", 100)
    return control.get_tool_audit(limit=limit)


def handle_inspect_integrations(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Inspect hub brain and WAHA connectivity/session visibility."""
    return control.inspect_integrations()


def handle_preview_autonomous_decision(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Run one dry-run autonomous loop iteration and return the decision output."""
    return control.preview_autonomous_decision()


def handle_run_stage(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Run a stage synchronously and return stdout/stderr/result."""
    params = params or {}
    stage = params.get("stage")
    if not stage:
        raise ValueError("stage is required")

    dry_run = params.get("dry_run", False)
    query = params.get("query")
    lead_id = params.get("lead_id")
    location = params.get("location")
    count = params.get("count")
    vertical = params.get("vertical")

    return control.run_stage(
        stage,
        dry_run=dry_run,
        query=query,
        lead_id=lead_id,
        location=location,
        count=count,
        vertical=vertical,
    )


def handle_start_background_stage(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Start a background job and return a job id plus log path."""
    params = params or {}
    stage = params.get("stage")
    if not stage:
        raise ValueError("stage is required")

    args = params.get("args", [])
    return control.start_background_stage(stage, args=args)


def handle_list_jobs(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """List background jobs started by the control plane."""
    return control.list_jobs()


def handle_get_job(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get one background job status plus tail of its log."""
    params = params or {}
    job_id = params.get("job_id")
    if not job_id:
        raise ValueError("job_id is required")

    tail_lines = params.get("tail_lines", 100)
    return control.get_job(job_id, tail_lines=tail_lines)


def handle_stop_job(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Stop a background job started by the control plane."""
    params = params or {}
    job_id = params.get("job_id")
    if not job_id:
        raise ValueError("job_id is required")

    return control.stop_job(job_id)


def handle_send_test_email(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Send a real email using the repo's outbound chain."""
    params = params or {}
    to = params.get("to")
    subject = params.get("subject")
    body = params.get("body")

    if not to or not subject or not body:
        raise ValueError("to, subject, and body are required")

    return control.send_test_email(to=to, subject=subject, body=body)


def handle_send_test_whatsapp(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Send a real WhatsApp message using WAHA/wacli fallback."""
    params = params or {}
    phone = params.get("phone")
    message = params.get("message")

    if not phone or not message:
        raise ValueError("phone and message are required")

    return control.send_test_whatsapp(phone=phone, message=message)


def handle_set_lead_status(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Update one lead's funnel status directly."""
    params = params or {}
    lead_id = params.get("lead_id")
    status = params.get("status")

    if not lead_id or not status:
        raise ValueError("lead_id and status are required")

    note = params.get("note", "")
    return control.set_lead_status(lead_id=lead_id, status=status, note=note)


def handle_update_lead_fields(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Update arbitrary lead fields from a JSON payload."""
    params = params or {}
    lead_id = params.get("lead_id")
    fields = params.get("fields")

    if not lead_id or not fields:
        raise ValueError("lead_id and fields are required")

    return control.update_lead_fields(lead_id=lead_id, fields=fields)


def handle_load_dataframe_snapshot(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Return a tabular snapshot of current leads for agents that prefer dataframe-like data."""
    params = params or {}
    limit = params.get("limit", 100)
    return control.load_dataframe_snapshot(limit=limit)


def handle_list_wa_sessions(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """List all WhatsApp sessions with WAHA + local DB status."""
    return control.list_wa_sessions()


def handle_create_wa_session(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create a new WhatsApp session in WAHA + register in local DB + configure webhooks."""
    params = params or {}
    session_name = params.get("session_name")
    if not session_name:
        raise ValueError("session_name is required")

    phone = params.get("phone", "")
    label = params.get("label", "")
    mode = params.get("mode", "cs")
    persona = params.get("persona", "")

    return control.create_wa_session(
        session_name, phone=phone, label=label, mode=mode, persona=persona
    )


def handle_delete_wa_session(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Delete a WhatsApp session from WAHA and local DB."""
    params = params or {}
    session_name = params.get("session_name")
    if not session_name:
        raise ValueError("session_name is required")

    return control.delete_wa_session(session_name)


def handle_get_wa_session_status(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get WAHA status for a specific WhatsApp session."""
    params = params or {}
    session_name = params.get("session_name")
    if not session_name:
        raise ValueError("session_name is required")

    return control.get_wa_session_status(session_name)


def handle_get_wa_qr_code(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get QR code for a WhatsApp session as base64 image."""
    params = params or {}
    session_name = params.get("session_name")
    if not session_name:
        raise ValueError("session_name is required")

    return control.get_wa_qr_code(session_name)


def handle_list_kb_entries(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """List knowledge base entries for a WA number."""
    params = params or {}
    wa_number_id = params.get("wa_number_id")
    if not wa_number_id:
        raise ValueError("wa_number_id is required")

    category = params.get("category")
    return control.list_kb_entries(wa_number_id, category=category)


def handle_add_kb_entry(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Add a new knowledge base entry."""
    params = params or {}
    wa_number_id = params.get("wa_number_id")
    category = params.get("category")
    question = params.get("question")
    answer = params.get("answer")

    if not all([wa_number_id, category, question, answer]):
        raise ValueError("wa_number_id, category, question, and answer are required")

    tags = params.get("tags", "")
    return control.add_kb_entry(wa_number_id, category, question, answer, tags=tags)


def handle_search_kb(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Search knowledge base using full-text search."""
    params = params or {}
    wa_number_id = params.get("wa_number_id")
    query = params.get("query")

    if not wa_number_id or not query:
        raise ValueError("wa_number_id and query are required")

    return control.search_kb(wa_number_id, query)


def handle_delete_kb_entry(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Delete a knowledge base entry by ID."""
    params = params or {}
    entry_id = params.get("entry_id")
    if entry_id is None:
        raise ValueError("entry_id is required")

    return control.delete_kb_entry(entry_id)


def handle_seed_kb(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Seed default BerkahKarya FAQ entries for a WA number (skips duplicates)."""
    params = params or {}
    wa_number_id = params.get("wa_number_id")
    if not wa_number_id:
        raise ValueError("wa_number_id is required")

    return control.seed_kb(wa_number_id)


def handle_list_active_conversations(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """List active conversations, optionally filtered by WA number."""
    params = params or {}
    wa_number_id = params.get("wa_number_id")
    return control.list_active_conversations(wa_number_id=wa_number_id)


def handle_get_conversation_history(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get message history for a conversation."""
    params = params or {}
    conversation_id = params.get("conversation_id")
    if conversation_id is None:
        raise ValueError("conversation_id is required")

    limit = params.get("limit", 50)
    return control.get_conversation_history(conversation_id, limit=limit)


def handle_resolve_conversation(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Mark a conversation as resolved."""
    params = params or {}
    conversation_id = params.get("conversation_id")
    if conversation_id is None:
        raise ValueError("conversation_id is required")

    return control.resolve_conversation(conversation_id)


def handle_escalate_conversation(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Escalate a conversation to human support (triggers Telegram alert)."""
    params = params or {}
    conversation_id = params.get("conversation_id")
    reason = params.get("reason")

    if conversation_id is None or not reason:
        raise ValueError("conversation_id and reason are required")

    return control.escalate_conversation(conversation_id, reason)


def handle_start_warmcall(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Start a warm-call outreach sequence for a contact."""
    params = params or {}
    phone = params.get("phone")
    name = params.get("name")
    context = params.get("context")

    if not all([phone, name, context]):
        raise ValueError("phone, name, and context are required")

    session_name = params.get("session_name")
    return control.start_warmcall(phone, name, context, session_name=session_name)


def handle_get_due_warmcall_followups(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get warm-call follow-ups that are currently due."""
    return control.get_due_warmcall_followups()


# ============================================================================
# Method Registry
# ============================================================================

MCP_METHODS = {
    "get_system_config": handle_get_system_config,
    "get_funnel_summary": handle_get_funnel_summary,
    "list_leads": handle_list_leads,
    "get_lead": handle_get_lead,
    "get_recent_events": handle_get_recent_events,
    "get_tool_audit": handle_get_tool_audit,
    "inspect_integrations": handle_inspect_integrations,
    "preview_autonomous_decision": handle_preview_autonomous_decision,
    "run_stage": handle_run_stage,
    "start_background_stage": handle_start_background_stage,
    "list_jobs": handle_list_jobs,
    "get_job": handle_get_job,
    "stop_job": handle_stop_job,
    "send_test_email": handle_send_test_email,
    "send_test_whatsapp": handle_send_test_whatsapp,
    "set_lead_status": handle_set_lead_status,
    "update_lead_fields": handle_update_lead_fields,
    "load_dataframe_snapshot": handle_load_dataframe_snapshot,
    "list_wa_sessions": handle_list_wa_sessions,
    "create_wa_session": handle_create_wa_session,
    "delete_wa_session": handle_delete_wa_session,
    "get_wa_session_status": handle_get_wa_session_status,
    "get_wa_qr_code": handle_get_wa_qr_code,
    "list_kb_entries": handle_list_kb_entries,
    "add_kb_entry": handle_add_kb_entry,
    "search_kb": handle_search_kb,
    "delete_kb_entry": handle_delete_kb_entry,
    "seed_kb": handle_seed_kb,
    "list_active_conversations": handle_list_active_conversations,
    "get_conversation_history": handle_get_conversation_history,
    "resolve_conversation": handle_resolve_conversation,
    "escalate_conversation": handle_escalate_conversation,
    "start_warmcall": handle_start_warmcall,
    "get_due_warmcall_followups": handle_get_due_warmcall_followups,
}


# ============================================================================
# Routes
# ============================================================================


@router.post("/", response_model=MCPResponse)
async def handle_mcp_call(request: Request) -> MCPResponse:
    """Handle MCP JSON-RPC 2.0 method calls.

    Processes incoming MCP requests, routes to appropriate handler,
    and returns JSON-RPC 2.0 compliant responses.
    """
    try:
        data = await request.json()

        # Validate JSON-RPC 2.0 structure
        if not isinstance(data, dict):
            return MCPResponse(
                jsonrpc="2.0",
                error=MCPError(
                    code=-32600,
                    message="Invalid Request",
                    data="Request must be a JSON object",
                ).dict(),
                id=data.get("id", 0) if isinstance(data, dict) else 0,
            )

        jsonrpc = data.get("jsonrpc", "2.0")
        method = data.get("method")
        params = data.get("params", {})
        req_id = data.get("id", 0)

        # Log request
        print(f"[MCP] Method: {method}, Params: {params}")

        # Validate method exists
        if not method:
            return MCPResponse(
                jsonrpc=jsonrpc,
                error=MCPError(
                    code=-32600,
                    message="Invalid Request",
                    data="method field is required",
                ).dict(),
                id=req_id,
            )

        if method not in MCP_METHODS:
            return MCPResponse(
                jsonrpc=jsonrpc,
                error=MCPError(
                    code=-32601,
                    message="Method not found",
                    data=f"Method '{method}' is not supported",
                ).dict(),
                id=req_id,
            )

        # Execute method
        handler = MCP_METHODS[method]

        try:
            result = handler(params or {})

            return MCPResponse(jsonrpc=jsonrpc, result=result, id=req_id)

        except ValueError as e:
            return MCPResponse(
                jsonrpc=jsonrpc,
                error=MCPError(
                    code=-32602, message="Invalid params", data=str(e)
                ).dict(),
                id=req_id,
            )

        except Exception as e:
            print(f"[MCP ERROR] Method {method} failed: {e}")
            return MCPResponse(
                jsonrpc=jsonrpc,
                error=MCPError(
                    code=-32603, message="Internal error", data=str(e)
                ).dict(),
                id=req_id,
            )

    except Exception as e:
        print(f"[MCP ERROR] Request processing failed: {e}")
        return MCPResponse(
            jsonrpc="2.0",
            error=MCPError(code=-32700, message="Parse error", data=str(e)).dict(),
            id=0,
        )


@router.get("/methods")
async def list_mcp_methods() -> Dict[str, Any]:
    """List all available MCP methods.

    Returns a list of supported MCP methods for discovery.
    """
    return {
        "methods": list(MCP_METHODS.keys()),
        "count": len(MCP_METHODS),
        "protocol": "JSON-RPC 2.0",
    }
