# 1ai-reach MCP Contract

## Server entrypoint

- File: `mcp_server.py`
- Default transport: `stdio`
- Optional HTTP transport: `streamable-http` on `/mcp`

## Tool groups

### Read-only
- `get_system_config`
- `get_funnel_summary`
- `list_leads`
- `get_lead`
- `get_recent_events`
- `get_tool_audit`
- `inspect_integrations`
- `list_jobs`
- `get_job`
- `load_dataframe_snapshot`

### Preview / decision support
- `preview_autonomous_decision`
- `run_stage` with `dry_run=true`

### Mutating / operational
- `run_stage`
- `start_background_stage`
- `stop_job`
- `set_lead_status`
- `update_lead_fields`
- `send_test_email`
- `send_test_whatsapp`

## Safety model

- Read tools are annotated `read_only_hint=true`
- Live send tools are annotated `destructive_hint=true, open_world_hint=true`
- Long-running stages should use background jobs
- `autonomous_loop` is protected by a singleton DB lock

## Backend state sources

- `scripts/state_manager.py`
  - `leads`
  - `event_log`
  - `control_jobs`
  - `control_locks`
  - `tool_audit`

## Notes for agent authors

1. Always call `inspect_integrations` before live delivery actions.
2. Prefer `preview_autonomous_decision` before `start_background_stage("autonomous_loop")`.
3. Use `get_tool_audit` and `get_job` for observability instead of scraping raw logs.
