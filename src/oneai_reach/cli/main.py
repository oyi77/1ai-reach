"""Click CLI for 1ai-reach pipeline management.

Provides command-line interface for:
- Starting/stopping pipeline stages
- Querying funnel state and leads
- Managing WhatsApp sessions
- Sending test messages
- Monitoring system status
"""

import json
import sys
from typing import Any, Optional

import click

from oneai_reach.infrastructure.legacy import agent_control


def format_json(data: Any) -> str:
    """Format data as pretty JSON."""
    return json.dumps(data, indent=2, default=str)


@click.group()
@click.version_option(version="1.0.0", prog_name="oneai-reach")
def cli() -> None:
    """1ai-reach - Cold outreach automation pipeline for BerkahKarya.

    Manage leads, execute pipeline stages, and monitor system status.
    """
    pass


# ============================================================================
# FUNNEL & LEADS COMMANDS
# ============================================================================


@cli.group()
def funnel() -> None:
    """Manage funnel and leads."""
    pass


@funnel.command()
def summary() -> None:
    """Show funnel summary."""
    try:
        result = agent_control.get_funnel_summary()
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@funnel.command()
@click.option("--status", default=None, help="Filter by lead status")
@click.option("--limit", default=100, help="Maximum number of leads to return")
def leads(status: Optional[str], limit: int) -> None:
    """List leads."""
    try:
        result = agent_control.list_leads(status=status, limit=limit)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@funnel.command()
@click.argument("lead_id")
def lead(lead_id: str) -> None:
    """Get lead details."""
    try:
        result = agent_control.get_lead(lead_id)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@funnel.command()
@click.argument("lead_id")
@click.argument("status")
@click.option("--note", default="", help="Status change note")
def set_status(lead_id: str, status: str, note: str) -> None:
    """Set lead status."""
    try:
        result = agent_control.set_lead_status(lead_id, status=status, note=note)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# PIPELINE STAGE COMMANDS
# ============================================================================


@cli.group()
def stages() -> None:
    """Execute pipeline stages."""
    pass


@stages.command()
@click.argument("stage")
@click.option("--args", multiple=True, help="Arguments to pass to stage")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
def run(stage: str, args: tuple, dry_run: bool) -> None:
    """Run a pipeline stage synchronously."""
    try:
        result = agent_control.run_stage(stage, args=list(args), dry_run=dry_run)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@stages.command()
@click.argument("stage")
@click.option("--args", multiple=True, help="Arguments to pass to stage")
def start(stage: str, args: tuple) -> None:
    """Start a pipeline stage in background."""
    try:
        result = agent_control.start_background_stage(stage, args=list(args))
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@stages.command(name="list")
def list_stages() -> None:
    """List available pipeline stages."""
    stages_list = [
        "strategy",
        "enricher",
        "researcher",
        "generator",
        "reviewer",
        "blaster",
        "reply_tracker",
        "closer",
        "followup",
        "sheets_sync",
        "orchestrator",
        "autonomous_loop",
        "cs_engine",
        "warmcall_engine",
        "conversation_cleanup",
    ]
    click.echo("Available pipeline stages:")
    for stage in stages_list:
        click.echo(f"  - {stage}")


# ============================================================================
# JOB MANAGEMENT COMMANDS
# ============================================================================


@cli.group()
def jobs() -> None:
    """Manage background jobs."""
    pass


@jobs.command(name="list")
def list_jobs() -> None:
    """List all background jobs."""
    try:
        result = agent_control.list_jobs()
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@jobs.command()
@click.argument("job_id")
@click.option("--tail", default=100, help="Number of log lines to show")
def logs(job_id: str, tail: int) -> None:
    """Get job logs."""
    try:
        result = agent_control.get_job(job_id, tail_lines=tail)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@jobs.command()
@click.argument("job_id")
def stop(job_id: str) -> None:
    """Stop a background job."""
    try:
        result = agent_control.stop_job(job_id)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# WHATSAPP SESSION COMMANDS
# ============================================================================


@cli.group()
def wa() -> None:
    """Manage WhatsApp sessions."""
    pass


@wa.command()
def sessions() -> None:
    """List WhatsApp sessions."""
    try:
        result = agent_control.list_wa_sessions()
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wa.command()
@click.argument("session_name")
@click.option("--phone", default=None, help="Phone number for session")
def create(session_name: str, phone: Optional[str]) -> None:
    """Create WhatsApp session."""
    try:
        result = agent_control.create_wa_session(
            session_name=session_name, phone_number=phone
        )
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wa.command()
@click.argument("session_name")
def delete(session_name: str) -> None:
    """Delete WhatsApp session."""
    try:
        result = agent_control.delete_wa_session(session_name)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wa.command()
@click.argument("session_name")
def status(session_name: str) -> None:
    """Get WhatsApp session status."""
    try:
        result = agent_control.get_wa_session_status(session_name)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wa.command()
@click.argument("session_name")
def qr(session_name: str) -> None:
    """Get WhatsApp session QR code."""
    try:
        result = agent_control.get_wa_qr_code(session_name)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# TEST COMMANDS
# ============================================================================


@cli.group()
def test() -> None:
    """Send test messages."""
    pass


@test.command()
@click.argument("email")
@click.argument("subject")
@click.argument("body")
def email(email: str, subject: str, body: str) -> None:
    """Send test email."""
    try:
        result = agent_control.send_test_email(to=email, subject=subject, body=body)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@test.command()
@click.argument("phone")
@click.argument("message")
def whatsapp(phone: str, message: str) -> None:
    """Send test WhatsApp message."""
    try:
        result = agent_control.send_test_whatsapp(phone=phone, message=message)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# SYSTEM COMMANDS
# ============================================================================


@cli.group()
def system() -> None:
    """System status and configuration."""
    pass


@system.command()
def config() -> None:
    """Show system configuration."""
    try:
        result = agent_control.get_system_config()
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@system.command()
def integrations() -> None:
    """Show integration status."""
    try:
        result = agent_control.inspect_integrations()
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@system.command()
@click.option("--limit", default=100, help="Number of events to show")
def events(limit: int) -> None:
    """Show recent system events."""
    try:
        result = agent_control.get_recent_events(limit=limit)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@system.command()
@click.option("--limit", default=100, help="Number of records to show")
def snapshot(limit: int) -> None:
    """Get dataframe snapshot."""
    try:
        result = agent_control.load_dataframe_snapshot(limit=limit)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@system.command()
@click.option("--limit", default=100, help="Number of audit entries to show")
def audit(limit: int) -> None:
    """Get tool audit log."""
    try:
        result = agent_control.get_tool_audit(limit=limit)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@system.command()
def preview() -> None:
    """Preview autonomous decision."""
    try:
        result = agent_control.preview_autonomous_decision()
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# KNOWLEDGE BASE COMMANDS
# ============================================================================


@cli.group()
def kb() -> None:
    """Manage knowledge base."""
    pass


@kb.command(name="list")
@click.argument("wa_number_id")
@click.option("--category", default=None, help="Filter by category")
def list_kb(wa_number_id: str, category: Optional[str]) -> None:
    """List knowledge base entries."""
    try:
        result = agent_control.list_kb_entries(wa_number_id, category=category)
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@kb.command()
@click.argument("category")
@click.argument("content")
@click.option("--tags", multiple=True, help="Tags for entry")
def add(category: str, content: str, tags: tuple) -> None:
    """Add knowledge base entry."""
    try:
        result = agent_control.add_kb_entry(
            category=category, content=content, tags=list(tags)
        )
        click.echo(format_json(result))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
