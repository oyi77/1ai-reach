# 1ai-reach Agent Control Skill

Use this skill when an AI agent needs to operate, inspect, or supervise the `1ai-reach` sales pipeline.

## What this skill gives you

- A structured **MCP control plane** via `mcp_server.py`
- A reusable Python backend in `agent_control.py`
- Safe read tools for funnel, leads, events, jobs, and integrations
- Controlled write/run tools for pipeline stages, status changes, and live channel tests

## Primary rule

**Inspect first, act second.**

Recommended sequence for agents:
1. `get_system_config`
2. `inspect_integrations`
3. `get_funnel_summary`
4. `preview_autonomous_decision` or `run_stage(..., dry_run=true)`
5. only then use live/destructive tools

## MCP server

### Public HTTPS endpoint (recommended for remote agents)
```
https://engage-mcp.aitradepulse.com/mcp
```

Required headers:
```
Content-Type: application/json
Accept: application/json, text/event-stream
```

Quick test:
```bash
curl -X POST https://engage-mcp.aitradepulse.com/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Claude Desktop / local agent (stdio)
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "1ai-reach": {
      "command": "/home/openclaw/.openclaw/workspace/1ai-reach/.venv/bin/python",
      "args": ["/home/openclaw/.openclaw/workspace/1ai-reach/mcp_server.py", "--transport", "stdio"]
    }
  }
}
```

### Start locally as HTTP MCP server
```bash
python3 mcp_server.py --transport http --host 127.0.0.1 --port 8766
```

Local HTTP MCP path:
```text
http://127.0.0.1:8766/mcp
```

## Available tools

### Read-only / orientation
- `get_system_config`
- `get_funnel_summary`
- `list_leads`
- `get_lead`
- `get_recent_events`
- `inspect_integrations`
- `list_jobs`
- `get_job`
- `load_dataframe_snapshot`

### Safe previews
- `preview_autonomous_decision`
- `run_stage(..., dry_run=true)`

### Stateful / destructive operations
- `run_stage`
- `start_background_stage`
- `stop_job`
- `set_lead_status`
- `update_lead_fields`
- `send_test_email`
- `send_test_whatsapp`

## Stage names for `run_stage`

- `strategy`
- `enricher`
- `researcher`
- `generator`
- `reviewer`
- `blaster`
- `reply_tracker`
- `closer`
- `followup`
- `sheets_sync`
- `orchestrator`
- `autonomous_loop`

## Typical agent workflows

### 1. Check system health
1. `get_system_config`
2. `inspect_integrations`
3. `get_funnel_summary`

### 2. Preview what the autonomous system would do
1. `preview_autonomous_decision`

### 3. Generate proposal for one lead
1. `get_lead(lead_id=...)`
2. `run_stage(stage="generator", lead_id="...", dry_run=true)`
3. `run_stage(stage="generator", lead_id="...", dry_run=false)`

### 4. Start long-running autonomous supervision
1. `start_background_stage(stage="autonomous_loop", args=[])`
2. `get_job(job_id=...)`
3. `stop_job(job_id=...)` when needed

### 5. Test live delivery channels
1. `inspect_integrations`
2. `send_test_email(...)`
3. `send_test_whatsapp(...)`

## Safety notes

- `send_test_email` and `send_test_whatsapp` are **live** sends
- `blaster`, `closer`, `followup`, and non-dry-run `orchestrator` affect real leads
- Prefer `dry_run=true` wherever supported
- Use `start_background_stage` for long-running operations instead of blocking the agent

## Backend layout

- `agent_control.py` — structured control API used by MCP tools
- `mcp_server.py` — MCP transport/server entrypoint
- `scripts/state_manager.py` — authoritative SQLite state
- `scripts/senders.py` — email + WhatsApp delivery
- `scripts/autonomous_loop.py` — continuous OODA loop

## Current channel behavior

- Email uses Brevo/SMTP/Gmail fallback chain from `scripts/senders.py`
- WhatsApp uses WAHA with hosted/direct fallback and working-session discovery

## When not to use this skill

- If you only need to edit implementation code, use normal repository editing workflows
- If you need browser-based dashboards, there is no dedicated web UI yet
