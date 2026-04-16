import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Base paths (absolute, relative to this file's location)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).parent
_ROOT = _SCRIPTS_DIR.parent  # 1ai-reach/
_HUB_DIR = Path("/home/openclaw/projects/berkahkarya-hub")
_HUB_SERVICES_JSON = _HUB_DIR / "config" / "services.json"

DATA_DIR = _ROOT / "data"
RESEARCH_DIR = DATA_DIR / "research"
PROPOSALS_DIR = _ROOT / "proposals" / "drafts"
LOGS_DIR = _ROOT / "logs"
LEADS_FILE = DATA_DIR / "leads.csv"
DB_FILE = DATA_DIR / "leads.db"

# ---------------------------------------------------------------------------
# Pipeline loop settings
# ---------------------------------------------------------------------------
LOOP_SLEEP_SECONDS = int(os.getenv("LOOP_SLEEP_SECONDS", "60"))
MIN_NEW_LEADS_THRESHOLD = int(os.getenv("MIN_NEW_LEADS_THRESHOLD", "10"))

# ---------------------------------------------------------------------------
# AI Models
# ---------------------------------------------------------------------------
GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "sonnet")
REVIEWER_MODEL = os.getenv("REVIEWER_MODEL", "sonnet")

# ---------------------------------------------------------------------------
# Payment & booking links
# ---------------------------------------------------------------------------
PAYMENT_LINK = os.getenv("PAYMENT_LINK", "https://berkahkarya.org/pay")
CALENDLY_LINK = os.getenv("CALENDLY_LINK", "https://calendly.com/berkahkarya/15min")

# ---------------------------------------------------------------------------
# Default verticals for autonomous scraping
# ---------------------------------------------------------------------------
DEFAULT_VERTICALS = [
    "Digital Agency",
    "Coffee Shop",
    "Restaurant",
    "Retail Store",
    "Hotel",
    "Clinic",
    "E-commerce",
    "Startup",
    "Property",
    "Education",
]


def _load_dotenv() -> None:
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()


def _load_hub_services() -> dict:
    if not _HUB_SERVICES_JSON.exists():
        return {}
    try:
        return json.loads(_HUB_SERVICES_JSON.read_text())
    except Exception:
        return {}


_HUB_SERVICES = _load_hub_services()
_WAHA_CFG = _HUB_SERVICES.get("waha", {})

# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

# ---------------------------------------------------------------------------
# Brevo (primary outbound — trusted IP, 300 emails/day free)
# ---------------------------------------------------------------------------
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
SMTP_FROM = os.getenv("SMTP_FROM", "BerkahKarya <marketing@berkahkarya.org>")

# ---------------------------------------------------------------------------
# Stalwart SMTP (fallback outbound — marketing@berkahkarya.org)
# ---------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "mail.berkahkarya.org")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "marketing")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# ---------------------------------------------------------------------------
# Gmail / gog (fallback)
# ---------------------------------------------------------------------------
GMAIL_ACCOUNT = os.getenv("GMAIL_ACCOUNT", "moliangellina@gmail.com")
GMAIL_KEYRING_PASSWORD = os.getenv("GMAIL_KEYRING_PASSWORD", "openclaw")
SHEET_ID = os.getenv("SHEET_ID", "10tRBCuRl_T6_nmdN1ycHaSRmsK-7jGKLtbJewKAUz_I")

# ---------------------------------------------------------------------------
# BerkahKarya Hub (FastAPI, port 9099)
# ---------------------------------------------------------------------------
HUB_URL = os.getenv("HUB_URL", "http://localhost:9099")
HUB_API_KEY = os.getenv("HUB_HUB_API_KEY", "")  # empty = dev mode (no auth)

# ---------------------------------------------------------------------------
# WAHA (WhatsApp HTTP API)
# ---------------------------------------------------------------------------
WAHA_URL = os.getenv(
    "WAHA_URL", _WAHA_CFG.get("domain_url", "https://waha.aitradepulse.com")
)
WAHA_DIRECT_URL = "https://waha.aitradepulse.com"
WAHA_API_KEY = os.getenv(
    "WAHA_API_KEY",
    _WAHA_CFG.get("api_key", "0673158ede14970b922f7e62075bd0f211490ca335111a9e"),
)
WAHA_DIRECT_API_KEY = os.getenv(
    "WAHA_DIRECT_API_KEY",
    os.getenv("WAHA_API_KEY", "0673158ede14970b922f7e62075bd0f211490ca335111a9e"),
)
WAHA_SESSION = os.getenv("WAHA_SESSION", _WAHA_CFG.get("default_session", "default"))
WAHA_OWN_NUMBER = os.getenv(
    "WAHA_OWN_NUMBER", _WAHA_CFG.get("wa_number", "6282247006969")
)

# ---------------------------------------------------------------------------
# Multi-number CS / Warmcall engine
# ---------------------------------------------------------------------------
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8766")
WAHA_WEBHOOK_PATH = "/webhook/waha"
WAHA_WEBHOOK_SECRET = os.getenv("WAHA_WEBHOOK_SECRET", "")
CS_REPLY_DELAY_SECONDS = int(os.getenv("CS_REPLY_DELAY_SECONDS", "3"))
CS_MAX_REPLIES_PER_MINUTE = int(os.getenv("CS_MAX_REPLIES_PER_MINUTE", "10"))
CS_ESCALATION_TELEGRAM = bool(int(os.getenv("CS_ESCALATION_TELEGRAM", "1")))
CS_DEFAULT_PERSONA = os.getenv(
    "CS_DEFAULT_PERSONA",
    "You are a helpful customer service agent for BerkahKarya. "
    "Answer questions about our services professionally in the same language the customer uses. "
    "If you cannot answer, politely escalate to a human agent.",
)
WARMCALL_FOLLOWUP_INTERVALS = [1, 3, 7, 14]  # days between follow-ups
WARMCALL_MAX_TURNS = int(os.getenv("WARMCALL_MAX_TURNS", "5"))
ENGINE_MODES = {"cold": "Cold Call", "cs": "Customer Service", "warmcall": "Warm Call"}

# ---------------------------------------------------------------------------
# n8n workflows (optional — leave N8N_MEETING_WF empty to skip)
# ---------------------------------------------------------------------------
N8N_BASE = "https://n8n.aitradepulse.com/webhook"
N8N_MEETING_WF = os.getenv("N8N_MEETING_WF", "")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

# ---------------------------------------------------------------------------
# Telegram (team alerts)
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Local LLM proxy (aitradepulse, port 20128)
# ---------------------------------------------------------------------------
AITRADEPULSE_API_KEY = os.getenv(
    "AITRADEPULSE_API_KEY", "sk-f0c1ddf471008e76-501723-c663b4ac"
)

# ---------------------------------------------------------------------------
# PaperClip (AI Company OS)
# ---------------------------------------------------------------------------
PAPERCLIP_URL = os.getenv("PAPERCLIP_URL", "http://localhost:3100")
PAPERCLIP_COMPANY_ID = os.getenv(
    "PAPERCLIP_COMPANY_ID", "33e1e20e-d9f2-45f2-b907-0579ab795942"
)
PAPERCLIP_AGENT_CMO = os.getenv(
    "PAPERCLIP_AGENT_CMO", "ea3bb337-656a-4158-804d-fa1f7fab6dbc"
)

# ---------------------------------------------------------------------------
# Aggregator domains to skip in scraper
# ---------------------------------------------------------------------------
AGGREGATOR_DOMAINS = {
    "clutch.co",
    "sortlist.com",
    "themanifest.com",
    "goodfirms.co",
    "upwork.com",
    "fiverr.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "youtube.com",
    "wikipedia.org",
    "blogspot.com",
    "medium.com",
    "wordpress.com",
    "kumparan.com",
    "detik.com",
    "kompas.com",
    "tribunnews.com",
    "bisnis.com",
    "kontan.co.id",
    "cnbcindonesia.com",
    "yelp.com",
    "yellowpages.com",
    "foursquare.com",
    "g2.com",
    "capterra.com",
    "trustpilot.com",
}
