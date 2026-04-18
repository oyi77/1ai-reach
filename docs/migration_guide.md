# Migration Guide: From Old Scripts to New Package Structure

## Overview

1ai-reach has been restructured from a flat script directory to a professional Python package following **Clean Architecture** principles. This guide helps you migrate from the old script-based workflow to the new unified CLI and API.

**Good news**: All old scripts still work! They've been converted to backward-compatible shims that call the new CLI under the hood.

---

## Quick Start

### Old Way (Still Works)
```bash
python3 scripts/scraper.py "Digital Agency in Jakarta"
python3 scripts/enricher.py
python3 scripts/generator.py
python3 scripts/blaster.py
```

### New Way (Recommended)
```bash
oneai-reach stages run scraper --args "Digital Agency in Jakarta"
oneai-reach stages run enricher
oneai-reach stages run generator
oneai-reach stages run blaster
```

Both work identically. The new way is cleaner and recommended for new code.

---

## Installation

### Step 1: Install the Package

```bash
cd /home/openclaw/.openclaw/workspace/1ai-reach
pip install -e .
```

This installs the `oneai-reach` CLI command globally.

### Step 2: Verify Installation

```bash
oneai-reach --help
```

You should see the main help text with available commands.

---

## Command Migration

### Pipeline Stages

All pipeline stages are now executed via the `stages` command group:

**Old:**
```bash
python3 scripts/scraper.py "Digital Agency in Jakarta"
python3 scripts/vibe_scraper.py "Digital Agency" "Jakarta" 20
python3 scripts/enricher.py
python3 scripts/researcher.py
python3 scripts/generator.py
python3 scripts/reviewer.py
python3 scripts/blaster.py
python3 scripts/reply_tracker.py
python3 scripts/converter.py
python3 scripts/followup.py
python3 scripts/sheets_sync.py
```

**New:**
```bash
oneai-reach stages run scraper --args "Digital Agency in Jakarta"
oneai-reach stages run vibe_scraper --args "Digital Agency" --args "Jakarta" --args "20"
oneai-reach stages run enricher
oneai-reach stages run researcher
oneai-reach stages run generator
oneai-reach stages run reviewer
oneai-reach stages run blaster
oneai-reach stages run reply_tracker
oneai-reach stages run closer
oneai-reach stages run followup
oneai-reach stages run sheets_sync
```

**List available stages:**
```bash
oneai-reach stages list
```

### Background Jobs

Run long-running stages in the background:

**Old:**
```bash
python3 scripts/autonomous_loop.py &
python3 scripts/cs_engine.py &
```

**New:**
```bash
oneai-reach stages start autonomous_loop
oneai-reach stages start cs_engine
```

**Manage background jobs:**
```bash
oneai-reach jobs list                    # List all jobs
oneai-reach jobs logs <job_id>           # View job logs
oneai-reach jobs stop <job_id>           # Stop a job
```

### Full Pipeline (Orchestrator)

**Old:**
```bash
python3 scripts/orchestrator.py "Digital Agency in Jakarta"
python3 scripts/orchestrator.py "Coffee Shop in Jakarta" --dry-run
python3 scripts/orchestrator.py --followup-only
python3 scripts/orchestrator.py --enrich-only
python3 scripts/orchestrator.py --sync-only
```

**New:**
```bash
oneai-reach stages run orchestrator --args "Digital Agency in Jakarta"
oneai-reach stages run orchestrator --args "Coffee Shop in Jakarta" --dry-run
oneai-reach stages run orchestrator --args "--followup-only"
oneai-reach stages run orchestrator --args "--enrich-only"
oneai-reach stages run orchestrator --args "--sync-only"
```

### Funnel & Lead Management

**Old:**
```bash
python3 -c "from leads import funnel_summary; funnel_summary()"
python3 -c "from leads import load_leads; print(load_leads())"
# Manual CSV editing
```

**New:**
```bash
oneai-reach funnel summary                           # Show funnel summary
oneai-reach funnel leads                             # List all leads
oneai-reach funnel leads --status contacted          # Filter by status
oneai-reach funnel leads --limit 50                  # Limit results
oneai-reach funnel lead <lead_id>                    # Get lead details
oneai-reach funnel set-status <lead_id> replied      # Update lead status
oneai-reach funnel set-status <lead_id> won --note "Closed deal"
```

### WhatsApp Session Management

**Old:**
```bash
# Manual WAHA API calls with curl
```

**New:**
```bash
oneai-reach wa sessions                              # List all sessions
oneai-reach wa create <session_name>                 # Create session
oneai-reach wa create <session_name> --phone +62xxx # Create with phone
oneai-reach wa delete <session_name>                 # Delete session
oneai-reach wa status <session_name>                 # Get session status
oneai-reach wa qr <session_name>                     # Get QR code
```

### Testing

**Old:**
```bash
# Manual testing with scripts
```

**New:**
```bash
oneai-reach test email user@example.com "Subject" "Body text"
oneai-reach test whatsapp +6281234567890 "Test message"
```

### System Monitoring

**Old:**
```bash
# Manual inspection of config files and logs
```

**New:**
```bash
oneai-reach system config                            # Show configuration
oneai-reach system integrations                      # Check integration status
oneai-reach system events --limit 50                 # Show recent events
oneai-reach system snapshot --limit 100              # Get dataframe snapshot
oneai-reach system audit --limit 100                 # Get tool audit log
oneai-reach system preview                           # Preview autonomous decision
```

### Knowledge Base Management

**Old:**
```bash
# Manual database queries
```

**New:**
```bash
oneai-reach kb list <wa_number_id>                   # List KB entries
oneai-reach kb list <wa_number_id> --category faq   # Filter by category
oneai-reach kb add faq "How to order?" --tags order,help
```

---

## Configuration Changes

### Environment Variables

Configuration now uses **prefixed environment variables** for better organization. The new system uses Pydantic Settings with validation.

#### Database & Storage (prefix: `DB_`)

**Old:**
```bash
LEADS_FILE=data/leads.csv
DATA_DIR=data
RESEARCH_DIR=data/research
PROPOSALS_DIR=proposals/drafts
```

**New:**
```bash
DB_LEADS_FILE=data/leads.csv
DB_DB_FILE=data/leads.db
DB_DATA_DIR=data
DB_RESEARCH_DIR=data/research
DB_PROPOSALS_DIR=proposals/drafts
DB_LOGS_DIR=logs
```

#### Pipeline Settings (prefix: `PIPELINE_`)

**Old:**
```bash
LOOP_SLEEP_SECONDS=60
MIN_NEW_LEADS_THRESHOLD=10
```

**New:**
```bash
PIPELINE_LOOP_SLEEP_SECONDS=60
PIPELINE_MIN_NEW_LEADS_THRESHOLD=10
```

#### LLM Settings (prefix: `LLM_`)

**Old:**
```bash
GENERATOR_MODEL=sonnet
REVIEWER_MODEL=sonnet
```

**New:**
```bash
LLM_GENERATOR_MODEL=sonnet
LLM_REVIEWER_MODEL=sonnet
```

#### Email Settings (prefix: `SMTP_`)

**Old:**
```bash
BREVO_API_KEY=your_key
SMTP_FROM=BerkahKarya <marketing@berkahkarya.org>
SMTP_HOST=mail.berkahkarya.org
SMTP_PORT=587
SMTP_USER=marketing
SMTP_PASSWORD=your_password
```

**New:**
```bash
SMTP_BREVO_API_KEY=your_key
SMTP_FROM=BerkahKarya <marketing@berkahkarya.org>
SMTP_HOST=mail.berkahkarya.org
SMTP_PORT=587
SMTP_USER=marketing
SMTP_PASSWORD=your_password
```

#### Gmail Settings (prefix: `GMAIL_`)

**Old:**
```bash
GOG_ACCOUNT=moliangellina@gmail.com
GOG_KEYRING_PASSWORD=openclaw
GOOGLE_SHEET_ID=10tRBCuRl_T6_nmdN1ycHaSRmsK-7jGKLtbJewKAUz_I
```

**New:**
```bash
GMAIL_ACCOUNT=moliangellina@gmail.com
GMAIL_KEYRING_PASSWORD=openclaw
GMAIL_SHEET_ID=10tRBCuRl_T6_nmdN1ycHaSRmsK-7jGKLtbJewKAUz_I
```

#### Hub Settings (prefix: `HUB_`)

**Old:**
```bash
HUB_URL=http://localhost:9099
HUB_API_KEY=
```

**New (same):**
```bash
HUB_URL=http://localhost:9099
HUB_API_KEY=
```

#### WAHA Settings (prefix: `WAHA_`)

**Old:**
```bash
WAHA_URL=https://waha.aitradepulse.com
WAHA_API_KEY=your_key
WAHA_SESSION=default
```

**New:**
```bash
WAHA_URL=https://waha.aitradepulse.com
WAHA_DIRECT_URL=https://waha.aitradepulse.com
WAHA_API_KEY=your_key
WAHA_DIRECT_API_KEY=your_key
WAHA_SESSION=default
WAHA_OWN_NUMBER=6282247006969
WAHA_WEBHOOK_PATH=/webhook/waha
WAHA_WEBHOOK_SECRET=
```

#### Customer Service Settings (prefix: `CS_`)

**Old:**
```bash
MCP_BASE_URL=http://localhost:8766
REPLY_DELAY_SECONDS=3
```

**New:**
```bash
CS_MCP_BASE_URL=http://localhost:8766
CS_REPLY_DELAY_SECONDS=3
CS_MAX_REPLIES_PER_MINUTE=10
CS_ESCALATION_TELEGRAM=true
CS_DEFAULT_PERSONA="You are a helpful customer service agent..."
CS_MAX_TURNS=5
```

#### n8n Settings (prefix: `N8N_`)

**Old:**
```bash
N8N_BASE=https://n8n.aitradepulse.com/webhook
N8N_MEETING_WF=
```

**New:**
```bash
N8N_BASE=https://n8n.aitradepulse.com/webhook
N8N_MEETING_WF=
N8N_WEBHOOK_URL=
```

#### Telegram Settings (prefix: `TELEGRAM_`)

**Old:**
```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

**New (same):**
```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

#### External API Settings

**Old:**
```bash
GOOGLE_API_KEY=
AITRADEPULSE_API_KEY=sk-f0c1ddf471008e76-501723-c663b4ac
```

**New (same):**
```bash
GOOGLE_API_KEY=
AITRADEPULSE_API_KEY=sk-f0c1ddf471008e76-501723-c663b4ac
```

#### PaperClip Settings (prefix: `PAPERCLIP_`)

**Old:**
```bash
PAPERCLIP_URL=http://localhost:3100
PAPERCLIP_COMPANY_ID=33e1e20e-d9f2-45f2-b907-0579ab795942
PAPERCLIP_AGENT_CMO=ea3bb337-656a-4158-804d-fa1f7fab6dbc
```

**New (same):**
```bash
PAPERCLIP_URL=http://localhost:3100
PAPERCLIP_COMPANY_ID=33e1e20e-d9f2-45f2-b907-0579ab795942
PAPERCLIP_AGENT_CMO=ea3bb337-656a-4158-804d-fa1f7fab6dbc
```

#### API Settings (prefix: `API_`)

**New (for FastAPI server):**
```bash
API_KEYS=key1,key2,key3
API_RATE_LIMIT_PER_MINUTE=100
API_RATE_LIMIT_ENABLED=true
```

### Settings File

Configuration is now managed via Pydantic Settings in `src/oneai_reach/config/settings.py`.

**To override settings:**
1. Set environment variables (recommended)
2. Or modify `.env` file

The system automatically loads `.env` from the project root and validates all settings at startup.

---

## Service Restart Instructions

### Using Systemd (Production)

If you're running 1ai-reach as systemd services, update the service files to use the new CLI:

**Step 1: Stop existing services**
```bash
sudo systemctl stop 1ai-reach-autonomous
sudo systemctl stop 1ai-reach-cs
sudo systemctl stop 1ai-reach-api
```

**Step 2: Update service files**

Edit `/etc/systemd/system/1ai-reach-autonomous.service`:
```bash
sudo nano /etc/systemd/system/1ai-reach-autonomous.service
```

Change:
```ini
[Service]
ExecStart=/usr/bin/python3 /path/to/1ai-reach/scripts/autonomous_loop.py
```

To:
```ini
[Service]
ExecStart=/usr/bin/oneai-reach stages start autonomous_loop
WorkingDirectory=/path/to/1ai-reach
```

Edit `/etc/systemd/system/1ai-reach-cs.service`:
```bash
sudo nano /etc/systemd/system/1ai-reach-cs.service
```

Change:
```ini
[Service]
ExecStart=/usr/bin/python3 /path/to/1ai-reach/scripts/cs_engine.py
```

To:
```ini
[Service]
ExecStart=/usr/bin/oneai-reach stages start cs_engine
WorkingDirectory=/path/to/1ai-reach
```

**Step 3: Reload systemd and restart services**
```bash
sudo systemctl daemon-reload
sudo systemctl start 1ai-reach-autonomous
sudo systemctl start 1ai-reach-cs
sudo systemctl start 1ai-reach-api
```

**Step 4: Verify services are running**
```bash
sudo systemctl status 1ai-reach-autonomous
sudo systemctl status 1ai-reach-cs
sudo systemctl status 1ai-reach-api
```

### Using Shell Scripts

Update your shell scripts to use the new CLI:

**Old `start_all.sh`:**
```bash
#!/bin/bash
python3 scripts/autonomous_loop.py &
python3 scripts/cs_engine.py &
```

**New `start_all.sh`:**
```bash
#!/bin/bash
oneai-reach stages start autonomous_loop
oneai-reach stages start cs_engine
```

Then restart:
```bash
./scripts/stop_all.sh
./scripts/start_all.sh
```

### Manual Process Management

**Stop old processes:**
```bash
pkill -f "python3 scripts/autonomous_loop.py"
pkill -f "python3 scripts/cs_engine.py"
```

**Start new processes:**
```bash
oneai-reach stages start autonomous_loop
oneai-reach stages start cs_engine
```

**Check running jobs:**
```bash
oneai-reach jobs list
```

### Docker/Container Deployments

Update your `Dockerfile` or `docker-compose.yml`:

**Old Dockerfile:**
```dockerfile
CMD ["python3", "scripts/autonomous_loop.py"]
```

**New Dockerfile:**
```dockerfile
CMD ["oneai-reach", "stages", "start", "autonomous_loop"]
```

**Old docker-compose.yml:**
```yaml
services:
  autonomous:
    command: python3 scripts/autonomous_loop.py
```

**New docker-compose.yml:**
```yaml
services:
  autonomous:
    command: oneai-reach stages start autonomous_loop
```

### Cron Jobs

Update your crontab to use the new CLI:

**Old crontab:**
```bash
# Edit crontab
crontab -e

# Old entries
0 */6 * * * cd /path/to/1ai-reach && python3 scripts/orchestrator.py "Coffee Shop Jakarta"
0 9 * * * cd /path/to/1ai-reach && python3 scripts/sheets_sync.py
```

**New crontab:**
```bash
# Edit crontab
crontab -e

# New entries
0 */6 * * * cd /path/to/1ai-reach && oneai-reach stages run orchestrator --args "Coffee Shop Jakarta"
0 9 * * * cd /path/to/1ai-reach && oneai-reach stages run sheets_sync
```

### Development Mode

For local development, start services manually:

**Terminal 1: FastAPI server**
```bash
python3 -m oneai_reach.api.main
```

**Terminal 2: Background jobs**
```bash
oneai-reach stages start autonomous_loop
oneai-reach stages start cs_engine
```

**Terminal 3: Monitor jobs**
```bash
watch -n 5 oneai-reach jobs list
```

---

## Data Migration

### No Migration Required

Your existing data works without changes:
- `data/leads.csv` - Lead database (unchanged format)
- `data/leads.db` - SQLite database (unchanged schema)
- `data/research/` - Research files (unchanged)
- `proposals/drafts/` - Proposal files (unchanged)
- `logs/` - Log files (new structured JSON format)

### Data Access

The new system uses repository pattern for data access, but maintains full backward compatibility:
- **SQLite**: `src/oneai_reach/infrastructure/database/sqlite_lead_repository.py`
- **CSV**: `src/oneai_reach/infrastructure/database/csv_lead_repository.py`

Both repositories read and write the same formats as the old scripts.

---

## Deprecation Schedule

### Phase 1: Compatibility Mode (Current)

**Status:** Active  
**Timeline:** April 2026 - June 2026

- Old scripts still work but show deprecation warnings
- Scripts are shims that call the new CLI
- No breaking changes
- Full backward compatibility maintained

**Action required:** Update your scripts and cron jobs to use new CLI commands.

### Phase 2: Warning Mode

**Timeline:** July 2026 - September 2026

- Deprecation warnings become more prominent
- Old scripts log warnings to system logs
- Documentation updated to show new commands only
- Support for old scripts continues but discouraged

**Action required:** Complete migration to new CLI.

### Phase 3: Removal

**Timeline:** October 2026+

- Old scripts removed from repository
- Only new CLI supported
- Breaking change for unmigrated users
- No backward compatibility for old script paths

**Action required:** Ensure all automation uses new CLI before this date.

---

## Troubleshooting

### Issue: `oneai-reach: command not found`

**Problem:** CLI not installed or not in PATH.

**Solution:**
```bash
cd /home/openclaw/.openclaw/workspace/1ai-reach
pip install -e .

# Verify installation
which oneai-reach
oneai-reach --version
```

### Issue: Old script shows deprecation warning

**Problem:** Using deprecated script path.

**Solution:** This is expected. The old script works but is deprecated. Use the new CLI:
```bash
# Old (deprecated)
python3 scripts/scraper.py "Query"

# New (recommended)
oneai-reach stages run scraper --args "Query"
```

### Issue: Import errors when running old scripts

**Problem:** Package not installed or Python path issues.

**Solution:**
```bash
# Reinstall package
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

### Issue: Environment variables not loading

**Problem:** `.env` file not found or not in correct location.

**Solution:**
```bash
# Check .env location (must be in project root)
ls -la .env

# Verify settings are loaded
oneai-reach system config

# Set variables manually if needed
export DB_LEADS_FILE=data/leads.csv
export GMAIL_ACCOUNT=moliangellina@gmail.com
```

### Issue: "Permission denied" errors

**Problem:** CLI not executable or wrong permissions.

**Solution:**
```bash
# Make CLI executable
chmod +x $(which oneai-reach)

# Or run with python
python -m oneai_reach.cli.main --help
```

### Issue: Old scripts still running in background

**Problem:** Cron jobs or systemd services using old scripts.

**Solution:**
```bash
# Check cron jobs
crontab -l | grep scripts/

# Update cron jobs
crontab -e

# Check systemd services
systemctl list-units | grep 1ai-reach

# Update systemd service files
sudo nano /etc/systemd/system/1ai-reach-*.service
sudo systemctl daemon-reload
sudo systemctl restart 1ai-reach-*
```

### Issue: Background jobs not starting

**Problem:** Job management system not initialized or conflicting jobs.

**Solution:**
```bash
# Check job status
oneai-reach jobs list

# Stop conflicting jobs
oneai-reach jobs stop <job_id>

# Restart job
oneai-reach stages start <stage_name>

# Check logs
oneai-reach jobs logs <job_id> --tail 100
```

### Issue: Configuration validation errors

**Problem:** Invalid environment variable values.

**Solution:**
```bash
# Check configuration
oneai-reach system config

# Common issues:
# - Invalid URLs (must include http:// or https://)
# - Invalid port numbers (must be 1-65535)
# - Invalid email addresses
# - Missing required API keys

# Fix in .env file
nano .env
```

### Issue: Database file not found

**Problem:** Data directory doesn't exist.

**Solution:**
```bash
# Create data directory
mkdir -p data/

# The database will be created automatically on first run
oneai-reach funnel summary
```

### Issue: API endpoints not responding

**Problem:** FastAPI server not running.

**Solution:**
```bash
# Check if server is running
curl http://localhost:8000/health

# If not running, start it
python3 -m oneai_reach.api.main

# Or check logs
tail -f logs/oneai_reach.log
```

### Issue: WhatsApp messages not sending

**Problem:** WAHA integration not configured or session not active.

**Solution:**
```bash
# Check WAHA configuration
oneai-reach system integrations

# Check WhatsApp sessions
oneai-reach wa sessions

# Check session status
oneai-reach wa status default

# Test WhatsApp sending
oneai-reach test whatsapp +6281234567890 "Test message"
```

### Issue: Email not sending

**Problem:** SMTP configuration incorrect or credentials invalid.

**Solution:**
```bash
# Check email configuration
oneai-reach system config | grep -i smtp

# Test email sending
oneai-reach test email test@example.com "Test Subject" "Test body"

# Check logs for errors
tail -f logs/oneai_reach.log | grep -i email
```

---

## FAQ

### Q: Do I need to migrate my data?

**A:** No. The new CLI uses the same data formats (leads.csv, leads.db, proposals, research files). Your existing data works without changes.

### Q: Will my integrations break?

**A:** No. All integrations (WAHA, Hub Brain, PaperClip, n8n, Gmail, Brevo) remain unchanged. Only the command-line interface changed.

### Q: Can I use both old and new commands during migration?

**A:** Yes. Old scripts are shims that call the new CLI, so both work during the compatibility period (until June 2026).

### Q: What about my cron jobs?

**A:** Update your crontab to use new CLI commands:

```bash
# Old
0 */6 * * * cd /path/to/1ai-reach && python3 scripts/orchestrator.py "Coffee Shop Jakarta"

# New
0 */6 * * * cd /path/to/1ai-reach && oneai-reach stages run orchestrator --args "Coffee Shop Jakarta"
```

### Q: How do I check if migration is complete?

**A:** Run these checks:

```bash
# 1. Verify CLI works
oneai-reach --version

# 2. Check no old scripts in cron
crontab -l | grep "scripts/"

# 3. Check no old scripts in systemd
systemctl list-units | grep scripts

# 4. Verify configuration loads
oneai-reach system config

# 5. Test a pipeline stage
oneai-reach stages run enricher --dry-run

# 6. Check background jobs
oneai-reach jobs list
```

### Q: What if I find a bug in the new CLI?

**A:** Report issues on GitHub or contact the maintainer. During the compatibility period, you can fall back to old scripts if needed.

### Q: Do I need to update my .env file?

**A:** The new system uses prefixed environment variables (e.g., `DB_`, `SMTP_`, `GMAIL_`). Old variables still work during compatibility mode, but new prefixes are recommended:

```bash
# Old (still works)
LEADS_FILE=data/leads.csv
GOG_ACCOUNT=moliangellina@gmail.com

# New (recommended)
DB_LEADS_FILE=data/leads.csv
GMAIL_ACCOUNT=moliangellina@gmail.com
```

### Q: How do I migrate my custom scripts that import from scripts/?

**A:** Update imports to use the new package structure:

```python
# Old
from scripts.leads import load_leads, save_leads
from scripts.config import LEADS_FILE
from scripts.senders import send_email

# New
from oneai_reach.domain.repositories import LeadRepository
from oneai_reach.config.settings import get_settings
from oneai_reach.infrastructure.messaging import EmailSender

# Example usage
settings = get_settings()
leads_file = settings.database.leads_file
```

### Q: Can I still use the dashboard?

**A:** Yes. The Next.js dashboard (port 8502) works with both old and new backends. No changes needed.

### Q: What about the MCP server?

**A:** The MCP server (`mcp_server.py`) works with the new CLI. No changes needed for agent control.

### Q: How do I run multiple pipeline stages in sequence?

**A:** Use the orchestrator or chain commands:

```bash
# Option 1: Use orchestrator (recommended)
oneai-reach stages run orchestrator --args "Coffee Shop Jakarta"

# Option 2: Chain commands manually
oneai-reach stages run scraper --args "Coffee Shop Jakarta" && \
oneai-reach stages run enricher && \
oneai-reach stages run generator && \
oneai-reach stages run blaster
```

### Q: How do I pass multiple arguments to a stage?

**A:** Use multiple `--args` flags:

```bash
oneai-reach stages run vibe_scraper --args "Digital Agency" --args "Jakarta" --args "20"
```

### Q: Can I run stages in dry-run mode?

**A:** Yes, use the `--dry-run` flag:

```bash
oneai-reach stages run orchestrator --args "Coffee Shop Jakarta" --dry-run
```

### Q: How do I monitor background jobs?

**A:** Use the jobs command group:

```bash
# List all jobs
oneai-reach jobs list

# View job logs
oneai-reach jobs logs <job_id> --tail 100

# Stop a job
oneai-reach jobs stop <job_id>
```

### Q: What's the difference between `stages run` and `stages start`?

**A:** 
- `stages run` - Runs synchronously (blocks until complete)
- `stages start` - Runs in background (returns job ID immediately)

```bash
# Synchronous (wait for completion)
oneai-reach stages run enricher

# Background (returns immediately)
oneai-reach stages start autonomous_loop
```

### Q: How do I update lead status from the CLI?

**A:** Use the funnel command group:

```bash
oneai-reach funnel set-status <lead_id> replied
oneai-reach funnel set-status <lead_id> won --note "Closed deal for $5000"
```

### Q: Can I filter leads by status?

**A:** Yes:

```bash
oneai-reach funnel leads --status contacted
oneai-reach funnel leads --status replied --limit 50
```

---

## Summary

| Aspect | Old | New |
|--------|-----|-----|
| **CLI** | `python3 scripts/scraper.py` | `oneai-reach stages run scraper` |
| **Command Groups** | N/A | `funnel`, `stages`, `jobs`, `wa`, `test`, `system`, `kb` |
| **Background Jobs** | Manual process management | `oneai-reach jobs list/stop` |
| **Config** | Flat `.env` file | Pydantic Settings with prefixes |
| **Environment Variables** | No prefixes | Prefixed (`DB_`, `SMTP_`, `GMAIL_`, etc.) |
| **Database** | SQLite + CSV | SQLite + CSV (unchanged) |
| **Logging** | Text logs | Structured JSON logs |
| **Architecture** | Flat scripts | Clean Architecture |
| **API** | Multiple servers | Unified FastAPI server |
| **Status** | Deprecated | Recommended |
| **Compatibility** | Until June 2026 | Native |

**Migration is optional but recommended.** Both old and new ways work identically during the compatibility period.

---

## Getting Help

- **Documentation:** 
  - [Architecture Overview](architecture.md) - System design and Clean Architecture principles
  - [Data Models](data_models.md) - Complete domain model reference
  - [API Reference](api_reference.md) - FastAPI endpoint documentation
- **CLI Help:** Run `oneai-reach --help` or `oneai-reach <command> --help`
- **System Status:** Run `oneai-reach system config` and `oneai-reach system integrations`
- **Logs:** Check `logs/oneai_reach.log` for structured JSON logs
- **GitHub Issues:** Report bugs or request features
- **Community:** Join the BerkahKarya Discord for support

---

## Quick Migration Checklist

Use this checklist to ensure complete migration:

- [ ] **Install CLI**: `pip install -e .`
- [ ] **Verify installation**: `oneai-reach --version`
- [ ] **Update .env file**: Add prefixed variables (optional during compatibility)
- [ ] **Update cron jobs**: Replace `python3 scripts/` with `oneai-reach stages run`
- [ ] **Update systemd services**: Replace script paths with CLI commands
- [ ] **Update shell scripts**: Replace script calls with CLI commands
- [ ] **Update Docker/containers**: Replace CMD with CLI commands
- [ ] **Test configuration**: `oneai-reach system config`
- [ ] **Test integrations**: `oneai-reach system integrations`
- [ ] **Test pipeline stage**: `oneai-reach stages run enricher --dry-run`
- [ ] **Test funnel access**: `oneai-reach funnel summary`
- [ ] **Test WhatsApp**: `oneai-reach wa sessions`
- [ ] **Test email**: `oneai-reach test email test@example.com "Test" "Body"`
- [ ] **Check background jobs**: `oneai-reach jobs list`
- [ ] **Verify no old scripts in cron**: `crontab -l | grep scripts/`
- [ ] **Verify no old scripts in systemd**: `systemctl list-units | grep scripts`
- [ ] **Update custom scripts**: Replace imports from `scripts/` with `oneai_reach.*`
- [ ] **Document changes**: Update internal documentation
- [ ] **Train team**: Share this migration guide with team members

---

## Next Steps

1. **Install the package**: `pip install -e .`
2. **Try the new CLI**: `oneai-reach --help`
3. **Run a test command**: `oneai-reach funnel summary`
4. **Update one service**: Start with a non-critical cron job or service
5. **Monitor logs**: `tail -f logs/oneai_reach.log`
6. **Gradually migrate**: Update remaining services over the compatibility period
7. **Read the docs**: [Architecture Overview](architecture.md), [Data Models](data_models.md), [API Reference](api_reference.md)

The new CLI provides better error messages, structured logging, job management, and a unified interface for all operations. Take advantage of the compatibility period (until June 2026) to migrate gradually and safely.
