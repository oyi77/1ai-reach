# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`1ai-reach` is a full cold outreach automation pipeline for **BerkahKarya**. It scrapes real business leads, enriches them with contact info, researches prospect pain points, generates personalized AI proposals (informed by hub brain memory), reviews them for quality, sends them via email + WhatsApp, tracks replies across both channels, converts warm leads to meetings, and runs follow-ups automatically — a complete outreach funnel connected to the BerkahKarya Hub.

## Running the Pipeline

**Important:** All scripts must be run from the **parent directory** of this repo (one level up from `1ai-reach/`).

```bash
# Full pipeline (Vibe + Google Places → enrich → research → generate → review → send → track → convert → follow-up → sync)
python3 1ai-reach/scripts/orchestrator.py "Digital Agency in Jakarta"

# Dry run (no sending — generate + review only)
python3 1ai-reach/scripts/orchestrator.py "Coffee Shop in Jakarta" --dry-run

# Follow-up cycle only (replies → convert → follow-up → sync)
python3 1ai-reach/scripts/orchestrator.py --followup-only

# Enrich + research existing leads only
python3 1ai-reach/scripts/orchestrator.py --enrich-only

# Sheet + brain sync only
python3 1ai-reach/scripts/orchestrator.py --sync-only

# Individual steps
python3 1ai-reach/scripts/vibe_scraper.py "Digital Agency" "Jakarta" 20
python3 1ai-reach/scripts/scraper.py "Coffee Shop in Jakarta"
python3 1ai-reach/scripts/enricher.py
python3 1ai-reach/scripts/researcher.py
python3 1ai-reach/scripts/generator.py
python3 1ai-reach/scripts/reviewer.py
python3 1ai-reach/scripts/blaster.py
python3 1ai-reach/scripts/reply_tracker.py
python3 1ai-reach/scripts/converter.py
python3 1ai-reach/scripts/followup.py
python3 1ai-reach/scripts/sheets_sync.py

# Funnel status report
python3 -c "from leads import funnel_summary; funnel_summary()"
```

## Architecture

### Shared layer (import from these — never duplicate logic)

| Module | Exports |
|---|---|
| `scripts/config.py` | All constants: paths, API keys, hub/WAHA/PaperClip/n8n config |
| `scripts/utils.py` | `parse_display_name(raw)`, `safe_filename(name)`, `draft_path(index, name)` |
| `scripts/leads.py` | `load_leads(path?)`, `save_leads(df, path?)`, `funnel_summary()`, `LEADS_FILE`, `FUNNEL_STAGES` |
| `scripts/senders.py` | `send_email(email, subject, body)`, `send_whatsapp(phone, message)` |
| `scripts/brain_client.py` | `search(query)`, `add(content, category)`, `get_strategy(vertical)`, `learn_outcome(...)`, `learn_batch_outcomes(df)` |

### Full Pipeline

```
vibe_scraper.py       → decision-maker leads (name, direct email, LinkedIn) via Vibe Prospecting MCP
scraper.py            → additional leads from Google Places
  → data/leads.csv
  → enricher.py       (email, phone, LinkedIn — AgentCash Minerva → scrape → pattern)
  → researcher.py     (pain points, services, tech stack → data/research/)
  → generator.py      (personalized proposals — brain-informed → proposals/drafts/)
  → reviewer.py       (Claude quality gate → marks reviewed / needs_revision)
  → generator.py      (re-generates needs_revision drafts)
  → blaster.py        (sends email + WhatsApp via WAHA API / wacli)
  → reply_tracker.py  (checks Gmail inbox + WAHA WA inbox for replies)
  → converter.py      (replied → meeting invite email + PaperClip issue + n8n trigger)
  → followup.py       (7-day follow-up → 14-day cold mark)
  → sheets_sync.py    (syncs all leads to Google Sheet "Investor" tab)
  → brain sync        (stores outcomes in hub brain for future proposal intelligence)
```

### Funnel Stages (in `status` column)

```
new → enriched → draft_ready → needs_revision → reviewed →
contacted → followed_up → replied → meeting_booked →
won / lost / cold / unsubscribed
```

### Script Responsibilities

1. **vibe_scraper.py** — Calls `claude -p --dangerously-skip-permissions` with Vibe Prospecting MCP. Gets company + decision maker name + direct email + LinkedIn. Deduplicates by website and email.
2. **scraper.py** — Google Places API → Yellow Pages ID → DuckDuckGo (filtered). 60 leads/run.
3. **enricher.py** — AgentCash Minerva → website scraping → email pattern guessing. Phone normalization to `+62xxx`. Email validation rejects image filenames.
4. **researcher.py** — Scrapes homepage + /about + /services. Detects services, gaps, tech stack. Saves full brief to `data/research/`.
5. **generator.py** — Queries hub brain for strategy intel first (`brain_client.get_strategy`). Then Claude `sonnet` → `gemini` → `oracle`. Loads research brief for personalized prompts.
6. **reviewer.py** — Claude reviews each proposal 1-10. Pass threshold: 6/10. Marks `reviewed` or `needs_revision`.
7. **blaster.py** — 30-day cooldown. Sends email via `senders.py` + WhatsApp. Marks `contacted`.
8. **senders.py** — Email: `gog` → `himalaya` → queue. WhatsApp: WAHA HTTP API → wacli fallback.
9. **reply_tracker.py** — `gog gmail search` → WAHA chats API → himalaya fallback. Marks `replied`.
10. **converter.py** — For `replied` leads: meeting invite email + PaperClip issue + n8n trigger. Marks `meeting_booked`.
11. **followup.py** — Day 7: follow-up. Day 14: final → marks `cold`.
12. **sheets_sync.py** — Clears + re-appends all leads to Google Sheet "Investor" tab (12 columns).
13. **brain_client.py** — HTTP client to hub `/brain/*`. Stores outcomes; queries strategy before generation.

## Hub Integration (`~/projects/berkahkarya-hub`, port 9099)

| Hub Service | How 1ai-reach Uses It |
|---|---|
| Brain API (`/brain/*`) | Strategy queries before generation; outcome storage after funnel events |
| WAHA (WhatsApp HTTP API) | Primary WA sender + reply inbox check (`http://5.189.138.144:3000`, key: `321`) |
| PaperClip | Creates issues for `replied` leads (hot leads → CMO agent) |
| n8n | Meeting booking workflow trigger (set `N8N_MEETING_WF` in `.env`) |

All hub config lives in `config.py` — never hardcode URLs or keys in scripts.

## Voice Features (WhatsApp Customer Service)

The system supports voice note replies for WhatsApp CS mode. Voice settings are configured per WA number.

### Voice Pipeline

```
Voice Input (OGG) → faster-whisper (STT) → cs_engine (AI response) → ChatterBox TTS (TTS) → WAHA (voice note)
```

### Voice Configuration (per WA number)

| Setting | Options | Description |
|---|---|---|
| `voice_enabled` | 0/1 | Enable/disable voice replies |
| `voice_reply_mode` | auto/voice_only/text_only | When to use voice vs text |
| `voice_language` | ms/id/en | TTS response language |

### Voice Scripts

| Script | Purpose |
|---|---|
| `scripts/voice_config.py` | Voice config constants (models, paths) |
| `scripts/audio_utils.py` | WAV ↔ OGG conversion |
| `scripts/stt_engine.py` | faster-whisper STT |
| `scripts/tts_engine.py` | ChatterBox Multilingual TTS |
| `scripts/voice_pipeline.py` | Orchestration layer |
| `scripts/senders.py` | `send_voice_note()` function |

### Voice API Endpoints

```
GET  /api/voice-config/<session_name>  → get voice config
PATCH /api/voice-config/<session_name> → update voice config
```

### Dashboard

Voice settings UI: `/voice-settings` — configure per-number voice settings from the dashboard.

All hub config lives in `config.py` — never hardcode URLs or keys in scripts.

## Key Details

**Proposal file format:**
```
---PROPOSAL---
[Professional email body in English — personalized to prospect]
---WHATSAPP---
[Short casual 3-4 sentence message in Indonesian]
```

**Research brief location:** `data/research/{index}_{name}.txt`

**`displayName`** stored as stringified dict `{"text": "Name"}`. Always use `parse_display_name()` from `utils.py`.

**All paths** are absolute via `config.py`. Never hardcode `"1ai-reach/..."` strings in scripts.

**gog env vars** set automatically: `GOG_KEYRING_PASSWORD=openclaw`, `GOG_ACCOUNT=moliangellina@gmail.com`

**LLM chain:** `claude -p --model sonnet` → `gemini` (broken) → `oracle` (needs Chrome DevTools 9222)

**Vibe Prospecting** — MCP at `https://vibeprospecting.explorium.ai/mcp`. Called via `claude -p --dangerously-skip-permissions`. Requires active Vibe account on claude.ai.

**Google Sheet** — ID: `10tRBCuRl_T6_nmdN1ycHaSRmsK-7jGKLtbJewKAUz_I`, tab: "Investor", columns A–L.

**Installed CLIs:** `wacli`, `himalaya`, `gog`, `npx agentcash@latest`, `claude`
