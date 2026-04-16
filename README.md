# 1ai-reach

Cold Calling & Lead Automation System for BerkahKarya.

## Features
1. **Scraping**: Google Maps & Web via AgentCash (stableenrich).
2. **Enrichment**: Email & Phone number extraction via Minerva/Apollo.
3. **Drafting**: AI-generated proposals and WhatsApp messages.
4. **Blasting**: Automated sending via `wacli` and `himalaya`.
5. **Voice Support**: Voice note replies with ChatterBox TTS for WhatsApp CS mode.
6. **Auto-Learn**: Self-improvement system that learns from conversation outcomes.

## Dashboard (Next.js)

The primary UI is a Next.js dashboard running on port 8502.

### Start Dashboard
```bash
cd dashboard
npm install
npm run dev
```

Access at: http://localhost:8502

### Dashboard Pages
- **Home**: System overview and service status
- **Funnel**: Lead pipeline visualization
- **Conversations**: WhatsApp conversation management
- **KB**: Knowledge base editor
- **Services**: Service control (webhook, autonomous loop)
- **Auto-Learn**: Self-improvement analytics and controls
- **Voice Settings**: Configure voice note responses per WA number
- **Pipeline Control**: Manual pipeline execution

## Directory Structure
- `dashboard/`: Next.js frontend (TypeScript + React)
- `scripts/`: Python modules for each step.
- `data/`: Lead databases (`leads.csv`).
- `proposals/`: Generated proposals.
- `logs/`: Execution logs.

## Voice Features (WhatsApp Customer Service)

The system supports voice note replies for WhatsApp CS mode. When enabled, customers can send voice notes and receive AI-generated voice responses.

### Voice Pipeline

```
Voice Input (OGG) → faster-whisper (STT) → cs_engine (AI response) → ChatterBox TTS (TTS) → WAHA (voice note)
```

### Configuration

Voice settings are configurable per WA number via the dashboard at `/voice-settings` or via API:

```
GET  /api/voice-config/<session_name>  → get voice config
PATCH /api/voice-config/<session_name> → update voice config
```

### Voice Settings

| Setting | Options | Description |
|---|---|---|
| `voice_enabled` | true/false | Enable/disable voice replies |
| `voice_reply_mode` | auto/voice_only/text_only | When to use voice vs text |
| `voice_language` | ms/id/en | TTS response language |

Default language is Indonesian (Bahasa Indonesia).

## Usage (via Telegram)
Tell Vilona:
- "Scrape leads for [Niche] in [City]"
- "Enrich our current leads"
- "Generate proposals for the leads"
- "Blast the leads"

## Agent Control (MCP)

`1ai-reach` now exposes an MCP control plane so other AI agents can inspect and operate the backend safely.

### Install MCP dependencies
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

### Start MCP over stdio
```bash
python3 mcp_server.py --transport stdio
```

### Start MCP over HTTP
```bash
python3 mcp_server.py --transport http --host 127.0.0.1 --port 8765
```

HTTP MCP endpoint:
```text
http://127.0.0.1:8765/mcp
```

### Main MCP capabilities
- Read funnel state and lead records
- Read control-plane audit history
- Inspect WAHA / hub brain integrations
- Preview autonomous decisions
- Run individual pipeline stages
- Start/stop/list long-running background jobs
- Send live test email / WhatsApp messages
- Enforce DB-backed job tracking and singleton loop ownership

See `SKILL.md` for the agent workflow and tool inventory.

Or run the orchestrator:
```bash
python3 scripts/orchestrator.py "Coffee Shop in Jakarta"
```

## Admin Control
Admin can monitor progress by asking Vilona for a "status update on 1ai-reach".
Vilona will report:
- Total leads found
- Leads enriched
- Proposals drafted
- Messages sent
