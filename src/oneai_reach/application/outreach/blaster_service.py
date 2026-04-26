"""Blaster service - sends proposals via email and WhatsApp."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from weasyprint import HTML

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

PROPOSAL_SUBJECT = "Collaboration Proposal from BerkahKarya"
COOLDOWN_DAYS = 30  # don't re-contact the same lead within this window


class BlasterService:
    """Service for sending proposals to leads via email and WhatsApp.

    Handles:
    - Cooldown period enforcement (30 days)
    - Multi-channel sending (email + WhatsApp)
    - Status tracking (contacted_at timestamp)
    - Draft file loading and parsing
    """

    def __init__(self, config: Settings):
        """Initialize blaster service.

        Args:
            config: Application settings
        """
        self.config = config
        self.proposals_dir = config.database.proposals_dir
        self.cooldown_days = COOLDOWN_DAYS

    def blast_proposals(
        self,
        df: pd.DataFrame,
        send_email_fn,
        send_whatsapp_fn,
        draft_path_fn,
        is_empty_fn,
        parse_display_name_fn,
    ) -> tuple[int, int, int]:
        """Send proposals to all eligible leads.

        Args:
            df: DataFrame with leads
            send_email_fn: Function to send email (from senders.py)
            send_whatsapp_fn: Function to send WhatsApp (from senders.py)
            draft_path_fn: Function to get draft file path (from utils.py)
            is_empty_fn: Function to check if value is empty (from utils.py)
            parse_display_name_fn: Function to parse display name (from utils.py)

        Returns:
            Tuple of (sent_count, skipped_cooldown, skipped_no_draft)
        """
        logger.info(f"Starting blast for {len(df)} leads")

        sent = 0
        skipped_cooldown = 0
        skipped_no_draft = 0

        for index, row in df.iterrows():
            name = parse_display_name_fn(row.get("displayName"))

            # Only send leads that passed the quality review gate
            status = str(row.get("status") or "")
            if status not in ("reviewed", "new", ""):
                # Skip leads in other pipeline stages
                if status not in ("nan", "none"):
                    skipped_cooldown += 1
                    continue

            if self._is_recently_contacted(row, is_empty_fn):
                logger.info(
                    f"[skip] {name} — contacted within last {self.cooldown_days} days"
                )
                skipped_cooldown += 1
                continue

            email = str(row.get("email") or "").strip()
            phone = str(
                row.get("internationalPhoneNumber") or row.get("phone") or ""
            ).strip()

            if is_empty_fn(email):
                email = ""
            if is_empty_fn(phone):
                phone = ""

            path = draft_path_fn(index, name)
            if not os.path.exists(path):
                logger.warning(f"[skip] {name} — no draft at {path}")
                skipped_no_draft += 1
                continue

            with open(path) as f:
                content = f.read()

            parts = content.split("---WHATSAPP---")
            proposal = parts[0].replace("---PROPOSAL---", "").strip()
            wa_draft = parts[1].strip() if len(parts) > 1 else proposal

            logger.info(f"Processing: {name}")
            wa_sent = False
            email_sent = False

            # Convert proposal to PDF
            pdf_bytes = self._generate_pdf_from_html(proposal, name)

            if phone:
                wa_sent = send_whatsapp_fn(phone, wa_draft)

            if email:
                # Send email with PDF attachment
                email_sent = send_email_fn(email, PROPOSAL_SUBJECT, proposal, pdf_bytes=pdf_bytes, filename=f"Proposal_{name.replace(' ', '_')}.pdf")

            if wa_sent or email_sent:
                df.at[index, "status"] = "contacted"
                df.at[index, "contacted_at"] = datetime.now(timezone.utc).isoformat()
                sent += 1

        logger.info(
            f"Blast complete: {sent} sent, {skipped_cooldown} skipped (cooldown), "
            f"{skipped_no_draft} skipped (no draft)"
        )
        return sent, skipped_cooldown, skipped_no_draft

    def _generate_pdf_from_html(self, content: str, name: str) -> bytes:
        """Convert HTML content to PDF bytes."""
        html_wrapped = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 40px; color: #333; }}
                h1 {{ color: #1a1a2e; }}
                p {{ margin: 12px 0; }}
                .signature {{ margin-top: 24px; padding-top: 16px; border-top: 2px solid #ddd; }}
                .company {{ color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """
        return HTML(string=html_wrapped).write_pdf()

    def _is_recently_contacted(self, row: pd.Series, is_empty_fn) -> bool:
        """Check if lead was contacted within cooldown period.

        Args:
            row: Lead row from DataFrame
            is_empty_fn: Function to check if value is empty

        Returns:
            True if recently contacted, False otherwise
        """
        val = row.get("contacted_at")
        if is_empty_fn(val):
            return False
        try:
            contacted = datetime.fromisoformat(str(val)).replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - contacted < timedelta(
                days=self.cooldown_days
            )
        except Exception:
            return False
