# 1ai-reach MCP Safety Guide

## Safety tiers

### Tier 1 — Read-only
Safe by default:
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

### Tier 2 — Preview / dry-run
Preferred before mutating actions:
- `preview_autonomous_decision`
- `run_stage(..., dry_run=true)`

### Tier 3 — Mutating, internal state
- `set_lead_status`
- `update_lead_fields`
- `start_background_stage`
- `stop_job`

### Tier 4 — Live outbound / external side effects
- `run_stage(stage="blaster", dry_run=false)`
- `run_stage(stage="closer", dry_run=false)`
- `run_stage(stage="orchestrator", dry_run=false)`
- `send_test_email`
- `send_test_whatsapp`

## Rules for AI agents

1. Inspect integrations before live delivery.
2. Prefer dry-run before live pipeline execution.
3. Use `start_background_stage` for long-running work.
4. Do not start multiple autonomous loops; the backend enforces a singleton lock.
5. Use `get_tool_audit` and `get_recent_events` for traceability.

## Backend guarantees

- Background jobs are stored in SQLite (`control_jobs`)
- Loop ownership is protected by `control_locks`
- All control-plane mutations are recorded in `tool_audit`

## Known operational constraints

- Existing pipeline scripts still dual-write SQLite + CSV through `leads.py`
- Stage concurrency should remain conservative until all script paths are fully service-extracted
