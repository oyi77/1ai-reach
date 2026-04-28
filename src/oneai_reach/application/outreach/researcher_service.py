"""Prospect research service - extracts business logic from scripts/researcher.py."""

import os
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.llm.llm_client import LLMClient
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
}

_PAIN_SIGNALS = {
    "no_chatbot": lambda text: (
        not any(
            w in text.lower() for w in ["chat", "tawk", "crisp", "intercom", "whatsapp"]
        )
    ),
    "no_blog": lambda text: (
        not any(w in text.lower() for w in ["blog", "artikel", "news", "berita"])
    ),
    "no_testimonial": lambda text: (
        not any(
            w in text.lower()
            for w in ["testimoni", "review", "client", "klien", "case study"]
        )
    ),
    "no_cta": lambda text: (
        not any(
            w in text.lower()
            for w in [
                "contact us",
                "hubungi",
                "get started",
                "free consult",
                "konsultasi",
            ]
        )
    ),
    "no_portfolio": lambda text: (
        not any(
            w in text.lower()
            for w in ["portfolio", "proyek", "project", "our work", "hasil"]
        )
    ),
}

_TECH_SIGNALS = {
    "wordpress": "wp-content",
    "shopify": "shopify",
    "wix": "wix.com",
    "webflow": "webflow",
    "react": "react",
    "next.js": "__next",
    "google_ads": "googleads",
    "meta_pixel": "fbq(",
    "google_analytics": "gtag(",
}

_PAIN_LABELS = {
    "no_chatbot": "No live chat / WhatsApp widget on site",
    "no_blog": "No blog or content section (missing organic SEO leverage)",
    "no_testimonial": "No visible client testimonials or case studies",
    "no_cta": "Weak or missing call-to-action",
    "no_portfolio": "No portfolio / 'our work' section",
}


class ResearcherService:
    """Prospect pain-point research service.

    Scrapes prospect websites to identify:
      - Services offered
      - Target market
      - Visible pain points/gaps
      - Tech stack signals
    """

    def __init__(self, config: Settings):
        self.config = config
        self.research_dir = config.database.research_dir
        self.llm = LLMClient(config)

    def research_prospect(self, website: str) -> dict:
        """Research a prospect's website for pain points and services.

        Args:
            website: Prospect website URL

        Returns:
            Dictionary with services, pain_points, tech_stack, text_sample
        """
        if self._is_empty(website):
            return {}

        base = website if website.startswith("http") else "https://" + website
        pages = [
            base,
            base.rstrip("/") + "/about",
            base.rstrip("/") + "/services",
            base.rstrip("/") + "/tentang-kami",
            base.rstrip("/") + "/layanan",
        ]

        combined_html = ""
        combined_text = ""

        for url in pages:
            html = self._fetch(url)
            if html:
                combined_html += html
                combined_text += " " + self._clean_text(html)
            if len(combined_text) > 4000:
                break

        if not combined_text.strip():
            return {}

        services = self._extract_services(combined_text)
        pain_points = [
            label for label, check in _PAIN_SIGNALS.items() if check(combined_text)
        ]
        tech_stack = [
            name
            for name, signal in _TECH_SIGNALS.items()
            if signal.lower() in combined_html.lower()
        ]
        signals = self._detect_signals(combined_html, combined_text, base)

        decision_maker = "UNKNOWN"
        try:
            prompt = f"Analyze the following text scraped from a company website and identify the CEO, Founder, Co-Founder, or Owner. Reply ONLY with their full name. If not found, reply exactly with 'UNKNOWN'.\n\nText:\n{combined_text[:3000]}"
            result = self.llm.generate(prompt, fallback="UNKNOWN").strip()
            if result and result.upper() != "UNKNOWN" and len(result) < 50:
                decision_maker = result
                logger.info(f"Found decision maker on {base}: {decision_maker}")
        except Exception as e:
            logger.warning(f"Decision-Maker extraction failed for {base}: {e}")

        return {
            "services": services,
            "pain_points": pain_points,
            "tech_stack": tech_stack,
            "signals": signals,
            "decision_maker": decision_maker,
            "text_sample": combined_text[:800],
        }

    def _detect_signals(self, html: str, text: str, base_url: str) -> dict:
        """Detect service-matching signals from scraped HTML and text."""
        text_lower = text.lower()
        html_lower = html.lower()

        signals = {}
        signals["has_website"] = bool(html.strip())
        signals["website_status"] = "ok" if html.strip() else "unreachable"
        signals["has_ssl"] = base_url.startswith("https://")
        signals["page_speed_slow"] = len(html) > 500000
        signals["mobile_friendly"] = "viewport" in html_lower
        signals["has_seo"] = (
            "meta name=\"description\"" in html_lower
            or "meta property=\"og:" in html_lower
            or "<h1" in html_lower
        )
        signals["has_contact_form"] = any(
            x in html_lower for x in ["<form", "contact-form", "wpforms", "gravity-forms"]
        )
        signals["has_livechat"] = any(
            x in html_lower
            for x in [
                "tawk.to", "crisp.chat", "intercom", "zendesk",
                "livechat", "chatwoot", "whatsapp.com/widget",
            ]
        )
        social_patterns = [
            "facebook.com/", "instagram.com/", "twitter.com/",
            "x.com/", "tiktok.com/", "linkedin.com/", "youtube.com/",
        ]
        found_socials = []
        for pattern in social_patterns:
            if pattern in html_lower:
                found_socials.append(pattern.split(".")[0])
        signals["social_links"] = list(set(found_socials))
        signals["ads_detected"] = any(
            x in html_lower
            for x in ["googleads", "gtag(", "fbq(", "googleadservices", "doubleclick"]
        )
        signals["ecommerce_signals"] = any(
            x in html_lower
            for x in [
                "woocommerce", "shopify", "add to cart", "checkout",
                "shopping cart", "produk", "beli",
            ]
        )
        signals["booking_system"] = any(
            x in html_lower
            for x in [
                "booking.com", "calendly", "booknow", "reservasi",
                "reserv", "appointlet", "acuity",
            ]
        )
        return signals

    def format_research_brief(self, name: str, data: dict) -> str:
        """Format research data into a human-readable brief.

        Args:
            name: Prospect name
            data: Research data dictionary

        Returns:
            Formatted research brief text
        """
        if not data:
            return f"No research data available for {name}."

        lines = [f"# Prospect Research: {name}"]

        if data.get("decision_maker") and data["decision_maker"] != "UNKNOWN":
            lines.append(f"Decision Maker Found: {data['decision_maker']}")

        if data.get("services"):
            lines.append(f"Services detected: {', '.join(data['services'])}")

        if data.get("tech_stack"):
            lines.append(f"Tech stack: {', '.join(data['tech_stack'])}")

        if data.get("pain_points"):
            lines.append("Observed gaps/pain points:")
            for p in data["pain_points"]:
                lines.append(f"  - {_PAIN_LABELS.get(p, p)}")

        return "\n".join(lines)

    def save_research_brief(self, lead_index: int, name: str, brief: str) -> str:
        """Save research brief to file.

        Args:
            lead_index: Lead index/ID
            name: Lead name
            brief: Research brief text

        Returns:
            Path to saved file
        """
        os.makedirs(self.research_dir, exist_ok=True)
        safe_name = self._safe_filename(name)
        path = os.path.join(self.research_dir, f"{lead_index}_{safe_name}.txt")

        with open(path, "w") as f:
            f.write(brief)

        logger.info(f"Saved research brief to {path}")
        return path

    def _fetch(self, url: str, timeout: int = 8) -> Optional[str]:
        """Fetch HTML page content.

        Args:
            url: Page URL
            timeout: Request timeout in seconds

        Returns:
            HTML content or None if fetch fails
        """
        try:
            r = requests.get(
                url, headers=_HEADERS, timeout=timeout, allow_redirects=True
            )
            r.raise_for_status()
            return r.text
        except Exception:
            return None

    def _clean_text(self, html: str) -> str:
        """Extract and clean text from HTML.

        Args:
            html: HTML content

        Returns:
            Cleaned text (max 5000 chars)
        """
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "head"]):
            tag.decompose()
        return " ".join(soup.get_text(separator=" ").split())[:5000]

    def _extract_services(self, text: str) -> list[str]:
        """Extract service keywords from text.

        Args:
            text: Cleaned text content

        Returns:
            List of detected service keywords
        """
        keywords = [
            "SEO",
            "SEM",
            "Google Ads",
            "Meta Ads",
            "social media",
            "content marketing",
            "web development",
            "web design",
            "branding",
            "video production",
            "copywriting",
            "email marketing",
            "influencer",
            "KOL",
            "digital PR",
            "e-commerce",
            "mobile app",
            "UI/UX",
            "automation",
            "AI",
            "data analytics",
        ]
        return [k for k in keywords if k.lower() in text.lower()]

    @staticmethod
    def _is_empty(value) -> bool:
        """Check if value is effectively empty.

        Args:
            value: Value to check

        Returns:
            True if None, NaN, empty string, 'nan', or 'none'
        """
        if value is None:
            return True
        s = str(value).strip().lower()
        return s in ("", "nan", "none")

    @staticmethod
    def _safe_filename(name: str) -> str:
        """Convert name to filesystem-safe string.

        Args:
            name: Original name

        Returns:
            Filesystem-safe name
        """
        return "".join(c if c.isalnum() else "_" for c in str(name))
