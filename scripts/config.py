import sys
from pathlib import Path

# Get the project root directory (parent of scripts/)
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()

sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from oneai_reach.config.settings import get_settings

_settings = get_settings()

# Database and file storage - convert to absolute paths relative to project root
LEADS_FILE = (_PROJECT_ROOT / _settings.database.leads_file).resolve()
DB_FILE = (_PROJECT_ROOT / _settings.database.db_file).resolve()
DATA_DIR = (_PROJECT_ROOT / _settings.database.data_dir).resolve()
RESEARCH_DIR = (_PROJECT_ROOT / _settings.database.research_dir).resolve()
PROPOSALS_DIR = (_PROJECT_ROOT / _settings.database.proposals_dir).resolve()
LOGS_DIR = (_PROJECT_ROOT / _settings.database.logs_dir).resolve()

# Pipeline loop settings
LOOP_SLEEP_SECONDS = _settings.pipeline.loop_sleep_seconds
MIN_NEW_LEADS_THRESHOLD = _settings.pipeline.min_new_leads_threshold

# AI Models
GENERATOR_MODEL = _settings.llm.generator_model
REVIEWER_MODEL = _settings.llm.reviewer_model

# Payment & booking links
PAYMENT_LINK = _settings.booking.payment_link
CALENDLY_LINK = _settings.booking.calendly_link

# Default verticals for autonomous scraping
DEFAULT_VERTICALS = _settings.scraper.default_verticals
TARGET_LOCATIONS = _settings.scraper.target_locations

# API keys
GOOGLE_API_KEY = _settings.external_api.google_api_key

# Brevo (primary outbound)
BREVO_API_KEY = _settings.email.brevo_api_key
SMTP_FROM = _settings.email.smtp_from

# Stalwart SMTP (fallback outbound)
SMTP_HOST = _settings.email.smtp_host
SMTP_PORT = _settings.email.smtp_port
SMTP_USER = _settings.email.smtp_user
SMTP_PASSWORD = _settings.email.smtp_password

# Gmail / gog (fallback)
GMAIL_ACCOUNT = _settings.gmail.account
GMAIL_KEYRING_PASSWORD = _settings.gmail.keyring_password
SHEET_ID = _settings.gmail.sheet_id

# BerkahKarya Hub (FastAPI, port 9099)
HUB_URL = _settings.hub.url
HUB_API_KEY = _settings.hub.api_key

# WAHA (WhatsApp HTTP API)
WAHA_URL = _settings.waha.url
WAHA_DIRECT_URL = _settings.waha.direct_url
WAHA_API_KEY = _settings.waha.api_key
WAHA_DIRECT_API_KEY = _settings.waha.direct_api_key
WAHA_SESSION = _settings.waha.session
WAHA_OWN_NUMBER = _settings.waha.own_number

# Multi-number CS / Warmcall engine
MCP_BASE_URL = _settings.cs.mcp_base_url
WAHA_WEBHOOK_PATH = _settings.waha.webhook_path
WAHA_WEBHOOK_SECRET = _settings.waha.webhook_secret
CS_REPLY_DELAY_SECONDS = _settings.cs.reply_delay_seconds
CS_MAX_REPLIES_PER_MINUTE = _settings.cs.max_replies_per_minute
CS_ESCALATION_TELEGRAM = _settings.cs.escalation_telegram
CS_DEFAULT_PERSONA = _settings.cs.default_persona
WARMCALL_FOLLOWUP_INTERVALS = [1, 3, 7, 14]
WARMCALL_MAX_TURNS = _settings.cs.max_turns
ENGINE_MODES = {"cold": "Cold Call", "cs": "Customer Service", "warmcall": "Warm Call"}

# n8n workflows
N8N_BASE = _settings.n8n.base
N8N_MEETING_WF = _settings.n8n.meeting_wf
N8N_WEBHOOK_URL = _settings.n8n.webhook_url

# Telegram (team alerts)
TELEGRAM_BOT_TOKEN = _settings.telegram.bot_token
TELEGRAM_CHAT_ID = _settings.telegram.chat_id

# Local LLM proxy (aitradepulse, port 20128)
AITRADEPULSE_API_KEY = _settings.external_api.aitradepulse_api_key

# PaperClip (AI Company OS)
PAPERCLIP_URL = _settings.paperclip.url
PAPERCLIP_COMPANY_ID = _settings.paperclip.company_id
PAPERCLIP_AGENT_CMO = _settings.paperclip.agent_cmo

# Aggregator domains to skip in scraper
AGGREGATOR_DOMAINS = _settings.scraper.aggregator_domains

# gosom Google Maps scraper (Docker, port 8082)
GMAPS_SCRAPER_URL = _settings.scraper.gmaps_scraper_url
