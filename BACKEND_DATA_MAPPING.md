# Backend Data Mapping for WAHA Assignments & Outreach Tracker

**Date**: 2026-04-21  
**Purpose**: Document where WAHA session→persona mapping and outreach artifacts (research briefs, proposals, sent messages) are stored for implementing missing FastAPI endpoints.

---

## 1. WAHA Session → Persona Mapping

### Storage Location
**Database**: `data/1ai_reach.db` (primary) or `data/leads.db` (fallback)  
**Table**: `wa_numbers`

### Schema
```sql
CREATE TABLE wa_numbers (
    id TEXT PRIMARY KEY,
    session_name TEXT UNIQUE NOT NULL,
    phone TEXT,
    label TEXT,
    mode TEXT DEFAULT 'cs',
    kb_enabled INTEGER DEFAULT 1,
    auto_reply INTEGER DEFAULT 1,
    persona TEXT,                          -- ✅ PERSONA STORED HERE
    status TEXT DEFAULT 'inactive',
    webhook_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    voice_enabled INTEGER DEFAULT 0,
    voice_reply_mode TEXT DEFAULT 'auto',
    voice_language TEXT DEFAULT 'ms'
);
```

### Current Data Sample
```
id      | session_name      | persona                                                          | mode
--------|-------------------|------------------------------------------------------------------|-----
wa_001  | default           | You are a friendly customer service representative for BK...    | cs
wa_002  | Detergen          | You are a professional customer service agent for Berkah...     | cs
wa_003  | produk_digital    | You are a helpful assistant for digital product sales...        | cs
wa_004  | warung_kecantikan | You are a friendly beauty shop assistant...                     | cs
```

### Access Methods
- **Python**: `scripts/state_manager.py`
  - `get_wa_numbers()` → list all sessions
  - `get_wa_number_by_session(session_name)` → get single session
  - `upsert_wa_number(session_name, **fields)` → create/update

- **API**: `webhook_server.py` (Flask - legacy)
  - `GET /api/wa-numbers` → list all sessions

---

## 2. Conversations → Lead Mapping

### Storage Location
**Database**: `data/1ai_reach.db`  
**Table**: `conversations`

### Schema
```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wa_number_id TEXT,                     -- ✅ Links to wa_numbers.id
    contact_phone TEXT NOT NULL,
    contact_name TEXT,
    lead_id TEXT,                          -- ✅ Links to leads.id
    engine_mode TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    manual_mode INTEGER DEFAULT 0,
    test_mode INTEGER DEFAULT 0,
    last_message_at TEXT,
    message_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id)
);
```

### Conversation Messages
**Table**: `conversation_messages`
```sql
CREATE TABLE conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,               -- ✅ Links to conversations.id
    direction TEXT NOT NULL,               -- 'inbound' or 'outbound'
    message_text TEXT,
    message_type TEXT DEFAULT 'text',
    waha_message_id TEXT,
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
```

### Access Methods
- **Python**: `scripts/state_manager.py`
  - `get_or_create_conversation(wa_number_id, contact_phone, engine_mode)` → int (conversation_id)
  - `get_conversation_messages(conversation_id, limit=50)` → list[dict]
  - `add_conversation_message(conversation_id, direction, message_text, ...)` → int (message_id)

---

## 3. Research Briefs Storage

### Storage Location
**Filesystem**: `data/research/`  
**Naming Pattern**: `{lead_id}_{safe_name}.txt`

### Example Files
```
data/research/0_Rocket_Digital_Indonesia.txt
data/research/100_Tuang_Coffee.txt
data/research/102_Kedai_Kopi_Koeii.txt
```

### Content Format
```
# Prospect Research: Rocket Digital Indonesia
Services detected: SEO, social media, digital PR, e-commerce, AI
Tech stack: wordpress, react
Observed gaps/pain points:
  - No blog or content section (missing organic SEO leverage)
```

### Generation & Access
- **Generator**: `src/oneai_reach/application/outreach/researcher_service.py`
  - `save_research_brief(lead_index, name, brief)` → str (path)
  - Research is scraped from prospect websites
  - Detects services, tech stack, and pain points

- **Consumer**: `src/oneai_reach/application/outreach/generator_service.py`
  - `load_research(lead_id, name)` → str (research text)
  - Used when generating proposals

### Database Reference
**Table**: `leads` (in `data/leads.db`)  
**Column**: `research` (TEXT) - stores summary or "no_data"

---

## 4. Proposals Storage

### Storage Location
**Filesystem**: `proposals/drafts/`  
**Naming Pattern**: `{lead_id}_{safe_name}.txt`

### Example Files
```
proposals/drafts/4_ToffeeDev___Digital_Marketing_Agency_Jakarta__Jasa_SEO__Ads__dan_Pembuatan_Website.txt
proposals/drafts/108_Mitra10_Daan_Mogot_Jakarta_Barat.txt
proposals/drafts/128_Test_New_Lead.txt
```

### Content Format
```
---PROPOSAL---
Subject: Helping ToffeeDev Scale Faster with AI Automation

Hi ToffeeDev Team,

[Professional email body in English]

---WHATSAPP---
[Short casual WhatsApp message in Indonesian]
```

### Generation & Access
- **Generator**: `src/oneai_reach/application/outreach/generator_service.py`
  - `generate_proposal(lead, dry_run=False)` → str (proposal text)
  - `save_proposal(lead_id, lead_name, proposal_text)` → Path
  - Uses LLM chain: claude → gemini → oracle

- **Configuration**: `src/oneai_reach/config/settings.py`
  - `config.database.proposals_dir` → Path to proposals directory

---

## 5. Sent Messages Tracking

### Email Tracking
**Database**: `data/leads.db`  
**Table**: `leads`

**Columns**:
```sql
contacted_at TEXT,              -- ✅ Timestamp when email was sent
email_message_id TEXT,          -- ✅ Brevo message ID
email_delivered_at TEXT,        -- Delivery confirmation
email_opened_at TEXT,           -- First open timestamp
email_clicked_at TEXT,          -- First click timestamp
email_open_count INTEGER DEFAULT 0,
email_click_count INTEGER DEFAULT 0,
email_bounce_reason TEXT
```

### WhatsApp Tracking
**Database**: `data/1ai_reach.db`  
**Table**: `conversation_messages`

**Query to get sent messages**:
```sql
SELECT cm.*, c.lead_id, c.wa_number_id
FROM conversation_messages cm
JOIN conversations c ON cm.conversation_id = c.id
WHERE cm.direction = 'outbound'
  AND c.lead_id IS NOT NULL
ORDER BY cm.timestamp DESC;
```

### Event Log
**Database**: `data/leads.db`  
**Table**: `event_log`

```sql
CREATE TABLE event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    event_type TEXT NOT NULL,           -- 'email_sent', 'whatsapp_sent', etc.
    details TEXT,                       -- JSON with message details
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);
```

### Access Methods
- **Python**: `scripts/state_manager.py`
  - `add_event_log(lead_id, event_type, details)` → None
  - `get_event_logs(lead_id=None, limit=100)` → list[dict]

---

## 6. Current API Endpoints

### Legacy Flask API (`webhook_server.py`)
```
GET  /api/leads                    → list all leads
GET  /api/leads/<lead_id>          → get lead details
PATCH /api/leads/<lead_id>         → update lead fields

GET  /api/wa-numbers               → list WAHA sessions
GET  /api/voice-config/<session>   → get voice config
PATCH /api/voice-config/<session>  → update voice config

GET  /api/kb/<wa_number_id>        → list KB entries
POST /api/kb/<wa_number_id>        → add KB entry
```

### FastAPI (`src/oneai_reach/api/v1/agents.py`)
```
GET  /api/v1/agents/leads          → list leads (with status filter)
GET  /api/v1/agents/leads/{id}     → get lead details + events
PATCH /api/v1/agents/leads/{id}/status  → update lead status
PATCH /api/v1/agents/leads/{id}/fields  → update lead fields

GET  /api/v1/agents/events         → get recent system events
```

---

## 7. Missing Endpoints Needed

### For WAHA Assignments Page
```
GET /api/v1/waha/sessions
→ List all WAHA sessions with persona, mode, status
→ Data: wa_numbers table

GET /api/v1/waha/sessions/{session_name}
→ Get single session details
→ Data: wa_numbers table

GET /api/v1/waha/sessions/{session_name}/conversations
→ List conversations for a session
→ Data: conversations + conversation_messages tables
→ Join: conversations.wa_number_id = wa_numbers.id

PATCH /api/v1/waha/sessions/{session_name}
→ Update session persona/config
→ Data: wa_numbers table
```

### For Detailed Outreach Tracker
```
GET /api/v1/leads/{lead_id}/research
→ Get research brief for a lead
→ Data: filesystem (data/research/{lead_id}_{name}.txt)
→ Fallback: leads.research column

GET /api/v1/leads/{lead_id}/proposal
→ Get proposal for a lead
→ Data: filesystem (proposals/drafts/{lead_id}_{name}.txt)

GET /api/v1/leads/{lead_id}/messages
→ Get all sent messages (email + WhatsApp) for a lead
→ Data: 
  - Email: leads table (contacted_at, email_message_id, email_*)
  - WhatsApp: conversation_messages (via conversations.lead_id)
  - Events: event_log table

GET /api/v1/leads/{lead_id}/timeline
→ Get complete timeline of interactions
→ Data: event_log + conversation_messages + email tracking
→ Merge and sort by timestamp
```

---

## 8. Implementation Checklist

### Step 1: Create WAHA Session Endpoints
- [ ] Create `src/oneai_reach/api/v1/waha.py`
- [ ] Add router to FastAPI app
- [ ] Implement `GET /api/v1/waha/sessions`
- [ ] Implement `GET /api/v1/waha/sessions/{session_name}`
- [ ] Implement `GET /api/v1/waha/sessions/{session_name}/conversations`
- [ ] Implement `PATCH /api/v1/waha/sessions/{session_name}`

### Step 2: Extend Lead Endpoints
- [ ] Add to `src/oneai_reach/api/v1/agents.py` or create `leads.py`
- [ ] Implement `GET /api/v1/leads/{lead_id}/research`
- [ ] Implement `GET /api/v1/leads/{lead_id}/proposal`
- [ ] Implement `GET /api/v1/leads/{lead_id}/messages`
- [ ] Implement `GET /api/v1/leads/{lead_id}/timeline`

### Step 3: Update React Dashboard
- [ ] Create `dashboard/src/pages/waha-assignments.tsx`
- [ ] Create `dashboard/src/pages/outreach-tracker.tsx`
- [ ] Add API client functions in `dashboard/src/lib/api.ts`
- [ ] Add navigation links in dashboard

---

## 9. Key Files Reference

### Database Access
- `scripts/state_manager.py` - All database CRUD operations
- `scripts/config.py` - Database file paths

### Service Layer
- `src/oneai_reach/application/outreach/researcher_service.py` - Research generation
- `src/oneai_reach/application/outreach/generator_service.py` - Proposal generation
- `src/oneai_reach/application/customer_service/cs_engine_service.py` - WhatsApp CS

### API Layer
- `webhook_server.py` - Legacy Flask API (backward compatible)
- `src/oneai_reach/api/v1/agents.py` - FastAPI agent endpoints
- `src/oneai_reach/api/v1/webhooks.py` - WAHA webhook handlers

### Configuration
- `src/oneai_reach/config/settings.py` - All config including paths
- `config.py` (scripts/) - Legacy config (still used)

---

## 10. Database Statistics (as of 2026-04-21)

```
Leads Total:        120
Contacted:          2
Research Briefs:    111 files
Proposals:          121 files
Conversations:      0 (in 1ai_reach.db)
WAHA Sessions:      4 active
```

---

## Summary

**WAHA Session → Persona Mapping**: Stored in `wa_numbers.persona` column in `data/1ai_reach.db`

**Research Briefs**: Stored as text files in `data/research/{lead_id}_{name}.txt`

**Proposals**: Stored as text files in `proposals/drafts/{lead_id}_{name}.txt`

**Sent Messages**:
- Email: Tracked in `leads` table columns (`contacted_at`, `email_message_id`, `email_*`)
- WhatsApp: Tracked in `conversation_messages` table (direction='outbound')
- Events: Logged in `event_log` table

**Next Steps**: Implement the missing FastAPI endpoints listed in Section 7 to expose this data to the React dashboard.
