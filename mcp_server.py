"""MCP server for controlling 1ai-reach.

Usage:
  python3 mcp_server.py --transport stdio
  python3 mcp_server.py --transport http --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json as _json
import sys as _sys
from collections import defaultdict
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

import agent_control as control  # noqa: E402  (also adds scripts/ to sys.path)
from config import WAHA_WEBHOOK_SECRET  # noqa: E402
from cs_engine import handle_inbound_message as cs_handle  # noqa: E402
from warmcall_engine import process_reply as warmcall_handle  # noqa: E402
from state_manager import (  # noqa: E402
    add_event_log,
    get_wa_number_by_session,
    upsert_wa_number,
)

# Track seen message IDs per session to prevent WAHA echo duplicates
_seen_messages: dict[str, set[str]] = defaultdict(set)

# Track running background tasks
_background_tasks: set = set()


def _is_duplicate_message(session: str, waha_message_id: str | None) -> bool:
    if not waha_message_id:
        return False
    if session not in _seen_messages:
        _seen_messages[session] = set()
    seen = _seen_messages[session]
    if waha_message_id in seen:
        return True
    seen.add(waha_message_id)
    _seen_messages[session] = {mid for mid in seen}
    return False


mcp = FastMCP(
    "1ai-reach",
    instructions=(
        "Control plane for BerkahKarya 1ai-reach. Use read-only tools to inspect "
        "funnel/lead state first. Prefer dry-run operations before destructive actions. "
        "Use background jobs for long-running stages like autonomous_loop."
    ),
)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def get_system_config() -> dict[str, Any]:
    """Return core runtime config relevant to agent control."""
    return control.get_system_config()


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def get_funnel_summary() -> dict[str, Any]:
    """Return funnel counts across all stages."""
    return control.get_funnel_summary()


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def list_leads(
    status: str | None = Field(
        default=None, description="Optional funnel status filter"
    ),
    limit: int = Field(default=100, description="Maximum leads to return"),
) -> dict[str, Any]:
    """List current leads from SQLite state."""
    return control.list_leads(status=status, limit=limit)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def get_lead(
    lead_id: str = Field(description="Exact lead id from SQLite"),
) -> dict[str, Any]:
    """Get one lead plus recent event log entries."""
    return control.get_lead(lead_id)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def get_recent_events(
    limit: int = Field(default=100, description="Maximum event log rows to return"),
) -> dict[str, Any]:
    """Return recent event log entries from the pipeline database."""
    return control.get_recent_events(limit=limit)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def get_tool_audit(
    limit: int = Field(
        default=100, description="Maximum control-plane audit rows to return"
    ),
) -> dict[str, Any]:
    """Return control-plane tool audit history."""
    return control.get_tool_audit(limit=limit)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=True
    )
)
def inspect_integrations() -> dict[str, Any]:
    """Inspect hub brain and WAHA connectivity/session visibility."""
    return control.inspect_integrations()


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def preview_autonomous_decision() -> dict[str, Any]:
    """Run one dry-run autonomous loop iteration and return the decision output."""
    return control.preview_autonomous_decision()


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
def run_stage(
    stage: str = Field(
        description="One of: strategy,enricher,researcher,generator,reviewer,blaster,reply_tracker,closer,followup,sheets_sync,orchestrator,autonomous_loop"
    ),
    dry_run: bool = Field(
        default=False, description="Enable safe dry-run when the stage supports it"
    ),
    query: str | None = Field(
        default=None, description="Required for orchestrator full/dry-run execution"
    ),
    lead_id: str | None = Field(
        default=None, description="Optional lead id for generator/closer"
    ),
    location: str | None = Field(
        default=None, description="Optional location for strategy stage"
    ),
    count: int | None = Field(
        default=None, description="Optional lead count for strategy stage"
    ),
    vertical: str | None = Field(
        default=None, description="Optional vertical override for strategy stage"
    ),
) -> dict[str, Any]:
    """Run a stage synchronously and return stdout/stderr/result."""
    return control.run_stage(
        stage,
        dry_run=dry_run,
        query=query,
        lead_id=lead_id,
        location=location,
        count=count,
        vertical=vertical,
    )


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def start_background_stage(
    stage: str = Field(
        description="Stage to run in background; best for autonomous_loop or long-running stages"
    ),
    args: list[str] = Field(
        default_factory=list, description="Raw CLI args to pass to the script"
    ),
) -> dict[str, Any]:
    """Start a background job and return a job id plus log path."""
    return control.start_background_stage(stage, args=args)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def list_jobs() -> dict[str, Any]:
    """List background jobs started by the control plane."""
    return control.list_jobs()


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def get_job(
    job_id: str = Field(
        description="Background job id returned by start_background_stage"
    ),
    tail_lines: int = Field(
        default=100, description="Number of trailing log lines to include"
    ),
) -> dict[str, Any]:
    """Get one background job status plus tail of its log."""
    return control.get_job(job_id, tail_lines=tail_lines)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def stop_job(
    job_id: str = Field(description="Background job id to terminate"),
) -> dict[str, Any]:
    """Stop a background job started by the control plane."""
    return control.stop_job(job_id)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
def send_test_email(
    to: str = Field(description="Recipient email address"),
    subject: str = Field(description="Email subject"),
    body: str = Field(description="Email body"),
) -> dict[str, Any]:
    """Send a real email using the repo's outbound chain."""
    return control.send_test_email(to=to, subject=subject, body=body)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
def send_test_whatsapp(
    phone: str = Field(description="Target phone number, Indonesian numbers supported"),
    message: str = Field(description="WhatsApp text body"),
) -> dict[str, Any]:
    """Send a real WhatsApp message using WAHA/wacli fallback."""
    return control.send_test_whatsapp(phone=phone, message=message)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def set_lead_status(
    lead_id: str = Field(description="Exact lead id"),
    status: str = Field(description="New funnel status"),
    note: str = Field(
        default="", description="Optional operator note recorded in event_log"
    ),
) -> dict[str, Any]:
    """Update one lead's funnel status directly."""
    return control.set_lead_status(lead_id=lead_id, status=status, note=note)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def update_lead_fields(
    lead_id: str = Field(description="Exact lead id"),
    fields_json: str = Field(description="JSON object of fields to update"),
) -> dict[str, Any]:
    """Update arbitrary lead fields from a JSON payload."""
    return control.update_lead_fields(
        lead_id=lead_id, fields=__import__("json").loads(fields_json)
    )


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def load_dataframe_snapshot(
    limit: int = Field(default=100, description="Maximum rows to include"),
) -> dict[str, Any]:
    """Return a tabular snapshot of current leads for agents that prefer dataframe-like data."""
    return control.load_dataframe_snapshot(limit=limit)


# ---------------------------------------------------------------------------
# WA Session management tools
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=True
    )
)
def list_wa_sessions() -> dict[str, Any]:
    """List all WhatsApp sessions with WAHA + local DB status."""
    return control.list_wa_sessions()


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
def create_wa_session(
    session_name: str = Field(description="Unique session name for WAHA"),
    phone: str = Field(
        default="", description="Phone number associated with this session"
    ),
    label: str = Field(default="", description="Human-readable label"),
    mode: str = Field(default="cs", description="Engine mode: cs, warmcall, or cold"),
    persona: str = Field(default="", description="Persona override for CS engine"),
) -> dict[str, Any]:
    """Create a new WhatsApp session in WAHA + register in local DB + configure webhooks."""
    return control.create_wa_session(
        session_name, phone=phone, label=label, mode=mode, persona=persona
    )


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
def delete_wa_session(
    session_name: str = Field(description="Session name to delete from WAHA + DB"),
) -> dict[str, Any]:
    """Delete a WhatsApp session from WAHA and local DB."""
    return control.delete_wa_session(session_name)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=True
    )
)
def get_wa_session_status(
    session_name: str = Field(description="Session name to query"),
) -> dict[str, Any]:
    """Get WAHA status for a specific WhatsApp session."""
    return control.get_wa_session_status(session_name)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=True
    )
)
def get_wa_qr_code(
    session_name: str = Field(description="Session name to get QR code for"),
) -> dict[str, Any]:
    """Get QR code for a WhatsApp session as base64 image."""
    return control.get_wa_qr_code(session_name)


# ---------------------------------------------------------------------------
# Knowledge Base tools
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def list_kb_entries(
    wa_number_id: str = Field(description="WA number ID to list entries for"),
    category: str | None = Field(
        default=None, description="Filter by category: faq, doc, snippet"
    ),
) -> dict[str, Any]:
    """List knowledge base entries for a WA number."""
    return control.list_kb_entries(wa_number_id, category=category)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def add_kb_entry(
    wa_number_id: str = Field(description="WA number ID to add entry for"),
    category: str = Field(description="Entry category: faq, doc, or snippet"),
    question: str = Field(description="Question or title"),
    answer: str = Field(description="Answer or content body"),
    tags: str = Field(default="", description="Comma-separated tags"),
) -> dict[str, Any]:
    """Add a new knowledge base entry."""
    return control.add_kb_entry(wa_number_id, category, question, answer, tags=tags)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def search_kb(
    wa_number_id: str = Field(description="WA number ID to search within"),
    query: str = Field(description="FTS5 search query"),
) -> dict[str, Any]:
    """Search knowledge base using full-text search."""
    return control.search_kb(wa_number_id, query)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def delete_kb_entry(
    entry_id: int = Field(description="KB entry ID to delete"),
) -> dict[str, Any]:
    """Delete a knowledge base entry by ID."""
    return control.delete_kb_entry(entry_id)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def seed_kb(
    wa_number_id: str = Field(description="WA number ID to seed default entries for"),
) -> dict[str, Any]:
    """Seed default BerkahKarya FAQ entries for a WA number (skips duplicates)."""
    return control.seed_kb(wa_number_id)


# ---------------------------------------------------------------------------
# Conversation management tools
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def list_active_conversations(
    wa_number_id: str | None = Field(
        default=None, description="Filter by WA number ID"
    ),
) -> dict[str, Any]:
    """List active conversations, optionally filtered by WA number."""
    return control.list_active_conversations(wa_number_id=wa_number_id)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def get_conversation_history(
    conversation_id: int = Field(description="Conversation ID"),
    limit: int = Field(default=50, description="Maximum messages to return"),
) -> dict[str, Any]:
    """Get message history for a conversation."""
    return control.get_conversation_history(conversation_id, limit=limit)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def resolve_conversation(
    conversation_id: int = Field(description="Conversation ID to resolve"),
) -> dict[str, Any]:
    """Mark a conversation as resolved."""
    return control.resolve_conversation(conversation_id)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
def escalate_conversation(
    conversation_id: int = Field(description="Conversation ID to escalate"),
    reason: str = Field(description="Reason for escalation"),
) -> dict[str, Any]:
    """Escalate a conversation to human support (triggers Telegram alert)."""
    return control.escalate_conversation(conversation_id, reason)


# ---------------------------------------------------------------------------
# Warm call tools
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
def start_warmcall(
    phone: str = Field(description="Target phone number"),
    name: str = Field(description="Contact name"),
    context: str = Field(description="Context for the warm call sequence"),
    session_name: str | None = Field(default=None, description="WAHA session to use"),
) -> dict[str, Any]:
    """Start a warm-call outreach sequence for a contact."""
    return control.start_warmcall(phone, name, context, session_name=session_name)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def get_due_warmcall_followups() -> dict[str, Any]:
    """Get warm-call follow-ups that are currently due."""
    return control.get_due_warmcall_followups()


# ---------------------------------------------------------------------------
# WAHA Webhook endpoint — receives inbound WA messages + session status
# ---------------------------------------------------------------------------


def _validate_hmac(body: bytes, header_hmac: str | None) -> bool:
    """Return True if HMAC is valid (or no secret configured)."""
    if not WAHA_WEBHOOK_SECRET:
        return True
    if not header_hmac:
        return False
    expected = hmac.new(WAHA_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_hmac)


async def _process_webhook_event(session: str, event: str, payload: dict) -> None:
    """Background task — process webhook event after 200 is returned."""
    try:
        sender = str(payload.get("from") or payload.get("chatId") or "")

        if event == "session.status":
            status = str(payload.get("status") or "").lower()
            if session and status:
                upsert_wa_number(session, status=status)
            return

        if event in ("message", "message.any"):
            if not sender:
                return

            wa_number = get_wa_number_by_session(session)
            if not wa_number:
                return

            waha_msg_id = str(payload.get("id") or "")
            if _is_duplicate_message(session, waha_msg_id):
                return

            # Echo guard: block messages from the bot's own number
            # WAHA echoes outbound messages back as "message.any" inbound webhooks
            # Use fromMe flag — reliable indicator that this is an outbound echo
            if payload.get("fromMe"):
                return

            mode = wa_number.get("mode", "cold")
            body_text = str(payload.get("body") or "")

            wa_number_id = wa_number.get("id", "")

            if mode == "cs" and wa_number.get("auto_reply"):
                add_event_log(
                    lead_id="webhook",
                    event_type="inbound_cs",
                    details=_json.dumps(
                        {
                            "session": session,
                            "from": sender,
                            "body": body_text[:500],
                            "wa_number_id": wa_number_id,
                            "mode": mode,
                        }
                    ),
                )
                try:
                    result = await asyncio.to_thread(
                        cs_handle,
                        wa_number_id=wa_number_id,
                        contact_phone=sender,
                        message_text=body_text,
                        session_name=session,
                    )
                    add_event_log(
                        lead_id="webhook",
                        event_type="cs_response",
                        details=_json.dumps(result),
                    )
                except Exception as e:
                    print(f"[webhook] CS engine error: {e}", file=_sys.stderr)
                    add_event_log(
                        lead_id="webhook",
                        event_type="cs_error",
                        details=str(e)[:500],
                    )
            elif mode == "warmcall":
                add_event_log(
                    lead_id="webhook",
                    event_type="inbound_warmcall",
                    details=_json.dumps(
                        {
                            "session": session,
                            "from": sender,
                            "body": body_text[:500],
                            "wa_number_id": wa_number_id,
                            "mode": mode,
                        }
                    ),
                )
                try:
                    from state_manager import get_or_create_conversation

                    conv_id = get_or_create_conversation(
                        wa_number_id=wa_number_id,
                        contact_phone=sender,
                        engine_mode="warmcall",
                    )
                    result = await asyncio.to_thread(
                        warmcall_handle,
                        conv_id,
                        body_text,
                    )
                    add_event_log(
                        lead_id="webhook",
                        event_type="warmcall_response",
                        details=_json.dumps(result),
                    )
                except Exception as e:
                    print(f"[webhook] Warmcall engine error: {e}", file=_sys.stderr)
                    add_event_log(
                        lead_id="webhook",
                        event_type="warmcall_error",
                        details=str(e)[:500],
                    )
    except Exception as e:
        print(f"[webhook] background error: {e}", file=_sys.stderr)


@mcp.custom_route("/webhook/waha", methods=["POST"])
async def webhook_waha(request: Request) -> JSONResponse:
    """Receive WAHA webhook events — inbound messages + session status."""
    try:
        body = await request.body()

        if WAHA_WEBHOOK_SECRET:
            header_hmac = request.headers.get("X-Webhook-Hmac")
            if not _validate_hmac(body, header_hmac):
                return JSONResponse({"error": "invalid hmac"}, status_code=401)

        try:
            data = _json.loads(body)
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)

        event = str(data.get("event") or "")
        session = str(data.get("session") or "")
        payload = data.get("payload") or {}

        add_event_log(
            lead_id="webhook",
            event_type="webhook_received",
            details=body.decode("utf-8", errors="replace")[:1000],
        )

        task = asyncio.create_task(_process_webhook_event(session, event, payload))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        return JSONResponse({"status": "ok", "event": event})

    except Exception as e:
        print(f"[webhook] error: {e}", file=_sys.stderr)
        return JSONResponse({"error": "internal error"}, status_code=500)


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server for 1ai-reach")
    parser.add_argument(
        "--transport", choices=["stdio", "http", "sse"], default="stdio"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        if args.transport == "sse":
            mcp.run(transport="sse")
        else:
            mcp.settings.streamable_http_path = "/mcp"
            mcp.settings.stateless_http = True
            mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
