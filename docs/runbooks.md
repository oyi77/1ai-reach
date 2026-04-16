# 1ai-reach Runbooks

## Start MCP for agent control

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python3 mcp_server.py --transport stdio
```

## Start MCP over HTTP

```bash
. .venv/bin/activate
python3 mcp_server.py --transport http --host 127.0.0.1 --port 8765
```

## Recommended agent sequence

1. `get_system_config`
2. `inspect_integrations`
3. `get_funnel_summary`
4. `preview_autonomous_decision`
5. `run_stage(..., dry_run=true)` or `start_background_stage(...)`

## Start autonomous loop under agent control

- Tool: `start_background_stage`
- Stage: `autonomous_loop`
- Follow-up: `get_job`, `list_jobs`, `stop_job`

## Send-channel verification

- Tool: `send_test_email`
- Tool: `send_test_whatsapp`

Always inspect WAHA sessions first via `inspect_integrations`.

## Lead intervention

- `get_lead`
- `set_lead_status`
- `update_lead_fields`

Use audit trail:
- `get_tool_audit`
- `get_recent_events`
