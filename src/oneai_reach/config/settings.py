"""
Type-safe configuration management using Pydantic Settings.

All configuration is loaded from environment variables with proper validation.
Use get_settings() to access the singleton instance.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional, Set

from pydantic import ConfigDict, Field, field_validator
import os
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """Database and file storage configuration."""

    leads_file: str = Field(
        default="data/leads.csv", description="Path to leads CSV file"
    )
    db_file: str = Field(default="data/leads.db", description="Path to SQLite database")
    data_dir: str = Field(default="data", description="Data directory path")
    research_dir: str = Field(
        default="data/research", description="Research output directory"
    )
    proposals_dir: str = Field(
        default="proposals/drafts", description="Proposals directory"
    )
    logs_dir: str = Field(default="logs", description="Logs directory")

    model_config = ConfigDict(env_prefix="DB_")


class PipelineSettings(BaseSettings):
    """Pipeline execution configuration."""

    loop_sleep_seconds: int = Field(
        default=60, description="Sleep duration between pipeline loops"
    )
    min_new_leads_threshold: int = Field(
        default=10, description="Minimum new leads to trigger pipeline"
    )

    model_config = ConfigDict(env_prefix="PIPELINE_")


class LLMSettings(BaseSettings):
    """Language model configuration."""

    generator_model: str = Field(
        default="sonnet", description="Model for proposal generation"
    )
    reviewer_model: str = Field(
        default="sonnet", description="Model for proposal review"
    )

    model_config = ConfigDict(env_prefix="LLM_")


class BookingSettings(BaseSettings):
    """Payment and booking links."""

    payment_link: str = Field(
        default="https://berkahkarya.org/pay", description="Payment link for prospects"
    )
    calendly_link: str = Field(
        default="https://calendly.com/berkahkarya/15min",
        description="Calendly booking link",
    )

    model_config = ConfigDict(env_prefix="BOOKING_")


class EmailSettings(BaseSettings):
    """Email configuration (Brevo + Stalwart SMTP)."""

    brevo_api_key: str = Field(
        default="", description="Brevo API key for email sending"
    )
    brevo_webhook_secret: str = Field(
        default="", description="Brevo webhook signature secret"
    )
    smtp_from: str = Field(
        default="BerkahKarya <marketing@berkahkarya.org>",
        description="From address for emails",
    )
    smtp_host: str = Field(
        default="mail.berkahkarya.org", description="SMTP server hostname"
    )
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: str = Field(default="marketing", description="SMTP username")
    smtp_password: str = Field(default="", description="SMTP password")

    model_config = ConfigDict(env_prefix="SMTP_")


class GmailSettings(BaseSettings):
    """Gmail and Google Sheets configuration."""

    account: str = Field(
        default="moliangellina@gmail.com", description="Gmail account email"
    )
    keyring_password: str = Field(
        default="openclaw", description="Keyring password for Gmail"
    )
    sheet_id: str = Field(
        default="10tRBCuRl_T6_nmdN1ycHaSRmsK-7jGKLtbJewKAUz_I",
        description="Google Sheet ID",
    )

    model_config = ConfigDict(env_prefix="GMAIL_")


class HubSettings(BaseSettings):
    """BerkahKarya Hub (FastAPI) configuration."""

    url: str = Field(default="http://localhost:9099", description="Hub base URL")
    api_key: str = Field(default="", description="Hub API key (empty = dev mode)")

    model_config = ConfigDict(env_prefix="HUB_")


class WAHASettings(BaseSettings):
    """WhatsApp HTTP API (WAHA) configuration."""

    url: str = Field(
        default="https://waha.aitradepulse.com", description="WAHA base URL"
    )
    direct_url: str = Field(
        default="https://waha.aitradepulse.com", description="Direct WAHA URL"
    )
    api_key: str = Field(
        default="199c96bcb87e45a39f6cde9e5677ed09",
        description="WAHA API key",
    )
    direct_api_key: str = Field(
        default="199c96bcb87e45a39f6cde9e5677ed09",
        description="Direct WAHA API key",
    )
    session: str = Field(
            default=os.environ.get("WAHA_SESSION", "default"), description="WAHA session name"
        )
    own_number: str = Field(default="6282247006969", description="Own WhatsApp number")
    webhook_path: str = Field(
        default="/webhook/waha", description="Webhook path for WAHA"
    )
    webhook_secret: str = Field(default="", description="Webhook secret for WAHA")

    model_config = ConfigDict(env_prefix="WAHA_")


class CustomerServiceSettings(BaseSettings):
    """Customer Service engine configuration."""

    mcp_base_url: str = Field(
        default="http://localhost:8766", description="MCP base URL"
    )
    reply_delay_seconds: int = Field(default=3, description="Delay before CS reply")
    max_replies_per_minute: int = Field(
        default=10, description="Max replies per minute"
    )
    escalation_telegram: bool = Field(default=True, description="Escalate to Telegram")
    default_persona: str = Field(
        default=(
            "You are a helpful customer service agent for BerkahKarya. "
            "Answer questions about our services professionally in the same language the customer uses. "
            "If you cannot answer, politely escalate to a human agent."
        ),
        description="Default CS persona",
    )
    max_turns: int = Field(default=5, description="Max conversation turns")

    model_config = ConfigDict(env_prefix="CS_")


class N8nSettings(BaseSettings):
    """n8n workflow configuration."""

    base: str = Field(
        default="https://n8n.aitradepulse.com/webhook", description="n8n base URL"
    )
    meeting_wf: str = Field(default="", description="Meeting workflow ID (optional)")
    webhook_url: str = Field(default="", description="n8n webhook URL")

    model_config = ConfigDict(env_prefix="N8N_")


class TelegramSettings(BaseSettings):
    """Telegram bot configuration."""

    bot_token: str = Field(default="", description="Telegram bot token")
    chat_id: str = Field(default="", description="Telegram chat ID")

    model_config = ConfigDict(env_prefix="TELEGRAM_")


class ExternalAPISettings(BaseSettings):
    """External API keys and services."""

    google_api_key: str = Field(default="", description="Google API key")
    aitradepulse_api_key: str = Field(
        default="sk-f0c1ddf471008e76-501723-c663b4ac",
        description="AiTradePulse API key",
    )
    exa_api_key: str = Field(
        default="", description="Exa API key for semantic intent search"
    )

    model_config = ConfigDict(env_prefix="")


class PaperClipSettings(BaseSettings):
    """PaperClip (AI Company OS) configuration."""

    url: str = Field(default="http://localhost:3100", description="PaperClip base URL")
    company_id: str = Field(
        default="33e1e20e-d9f2-45f2-b907-0579ab795942", description="Company ID"
    )
    agent_cmo: str = Field(
        default="ea3bb337-656a-4158-804d-fa1f7fab6dbc", description="CMO agent ID"
    )

    model_config = ConfigDict(env_prefix="PAPERCLIP_")


class ScraperSettings(BaseSettings):
    """Scraper configuration."""

    gmaps_scraper_url: str = Field(
        default="http://localhost:8082",
        description="gosom Google Maps scraper API URL",
    )
    aggregator_domains: Set[str] = Field(
        default={
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
        },
        description="Domains to skip in scraper",
    )
    default_verticals: list[str] = Field(
        default=[
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
        ],
        description="Default verticals for autonomous scraping",
    )

    model_config = ConfigDict(env_prefix="SCRAPER_")


class APISettings(BaseSettings):
    """API authentication and rate limiting configuration."""

    api_keys: str = Field(
        default="",
        description="Comma-separated list of valid API keys for authentication",
    )
    rate_limit_per_minute: int = Field(
        default=100, description="Max requests per minute per IP"
    )
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")

    model_config = ConfigDict(env_prefix="API_")

    def get_valid_keys(self) -> Set[str]:
        """Parse comma-separated API keys into a set."""
        if not self.api_keys:
            return set()
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}


class Settings(BaseSettings):
    """Root settings class combining all configuration groups."""

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    booking: BookingSettings = Field(default_factory=BookingSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    gmail: GmailSettings = Field(default_factory=GmailSettings)
    hub: HubSettings = Field(default_factory=HubSettings)
    waha: WAHASettings = Field(default_factory=WAHASettings)
    cs: CustomerServiceSettings = Field(default_factory=CustomerServiceSettings)
    n8n: N8nSettings = Field(default_factory=N8nSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    external_api: ExternalAPISettings = Field(default_factory=ExternalAPISettings)
    paperclip: PaperClipSettings = Field(default_factory=PaperClipSettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    api: APISettings = Field(default_factory=APISettings)

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get singleton Settings instance with caching."""
    return Settings()
