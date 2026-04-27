"""Contact enrichment service - extracts business logic from scripts/enricher.py."""

import json
import re
import subprocess
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger
from oneai_reach.infrastructure.web_reader import JinaWebReader
import asyncio

logger = get_logger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
}
_PHONE_RE = re.compile(r"(?:\+62|(?<!\d)62|08\d)\d{7,11}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_EMAIL_NOISE = {
    "example",
    "domain",
    "user@",
    "test@",
    "email@",
    "name@",
    "your@",
    "noreply@",
    "no-reply@",
    "sentry",
    "wixpress",
    "squarespace",
    "wordpress",
    "schema.org",
    "w3.org",
    "apple.com",
    "google.com",
}
_EMAIL_INVALID_EXTENSIONS = {
    ".webp",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".zip",
    ".mp4",
}
_CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/kontak",
    "/hubungi-kami",
    "/hubungi",
    "/about",
    "/tentang-kami",
    "/about-us",
    "/reach-us",
    "/get-in-touch",
]
_COMMON_EMAIL_PREFIXES = [
    "info",
    "contact",
    "hello",
    "admin",
    "marketing",
    "sales",
    "cs",
    "halo",
]


class EnricherService:
    """Multi-strategy contact enrichment service.

    Priority order per lead:
      1. AgentCash Minerva - paid, richest data
      2. Website contact pages - free scraping
      3. Mailto link scan - free, reliable email signal
      4. Common email patterns - free, guess and verify
    """

    def __init__(self, config: Settings):
        self.config = config

    def enrich_lead(self, website: str, name: str) -> Optional[dict]:
        """Enrich a single lead with contact information.

        Args:
            website: Business website URL
            name: Business/person name

        Returns:
            Dictionary with email, phone, linkedin or None if all strategies fail
        """
        if self._is_empty(website):
            return None

        research_data = None
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                import threading
                def run_async(coro):
                    res = []
                    def f():
                        res.append(asyncio.run(coro))
                    t = threading.Thread(target=f)
                    t.start()
                    t.join()
                    return res[0]
                research_data = run_async(JinaWebReader.fetch_markdown(website))
            else:
                research_data = loop.run_until_complete(JinaWebReader.fetch_markdown(website))
        except Exception as e:
            logger.warning(f"[JinaWebReader] failed to fetch markdown for {website}: {e}")

        strategies = [
            ("AgentCash Minerva", lambda: self._via_agentcash(website, name)),
            ("Website scraping", lambda: self._scrape_website(website)),
            ("Email pattern", lambda: self._guess_email(website, name)),
        ]

        for label, fn in strategies:
            try:
                result = fn()
                if result.get("email") or result.get("phone"):
                    logger.info(f"[{label}] found contact info")
                    result["research_data"] = research_data
                    return result
            except Exception as e:
                logger.warning(f"[{label}] failed: {e}")

        if research_data:
            return {"email": None, "phone": None, "linkedin": None, "research_data": research_data}

        return None

    def _via_agentcash(self, website: str, name: str) -> dict:
        """Enrich via AgentCash Minerva API (paid).

        Args:
            website: Business website
            name: Business/person name

        Returns:
            Dictionary with email, phone, linkedin

        Raises:
            RuntimeError: If enrichment fails or balance insufficient
        """
        result = subprocess.run(
            [
                "npx",
                "agentcash@latest",
                "fetch",
                "https://stableenrich.dev/api/minerva/enrich",
                "-m",
                "POST",
                "-b",
                json.dumps({"domain": website, "name": name}),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            try:
                err = json.loads(result.stdout)
                if err.get("error", {}).get("cause") == "insufficient_balance":
                    raise RuntimeError("AgentCash balance is zero - skipping")
            except (json.JSONDecodeError, AttributeError):
                pass
            raise RuntimeError("non-zero exit")

        data = json.loads(result.stdout)
        person = data.get("data", {}).get("person", {})

        if not person.get("email") and not person.get("phone"):
            raise RuntimeError("no contact info returned")

        return {
            "email": person.get("email"),
            "phone": person.get("phone"),
            "linkedin": person.get("linkedin_url"),
        }

    def _scrape_website(self, base_url: str) -> dict:
        """Scrape website for contact information.

        Args:
            base_url: Website base URL

        Returns:
            Dictionary with email, phone, linkedin

        Raises:
            RuntimeError: If no contact info found
        """
        if not base_url.startswith("http"):
            base_url = "https://" + base_url

        all_emails, all_phones = [], []
        pages_to_try = [base_url] + [urljoin(base_url, p) for p in _CONTACT_PATHS]

        for url in pages_to_try:
            html = self._fetch_page(url)
            if not html:
                continue

            emails = self._extract_mailto_emails(html) or self._extract_text_emails(
                html
            )
            phones = self._extract_phones(html)
            all_emails.extend(emails)
            all_phones.extend(phones)

            if all_emails:
                break

        if not all_emails and not all_phones:
            raise RuntimeError("no contact info found on website or contact pages")

        return {
            "email": all_emails[0] if all_emails else None,
            "phone": all_phones[0] if all_phones else None,
            "linkedin": None,
        }

    def _guess_email(self, website: str, person_name: str = "") -> dict:
        """Guess email using common patterns.

        Args:
            website: Business website
            person_name: Person name for name-based patterns

        Returns:
            Dictionary with guessed email

        Raises:
            RuntimeError: If domain extraction fails
        """
        try:
            domain = urlparse(
                website if website.startswith("http") else "https://" + website
            ).netloc
            domain = domain.lstrip("www.")
        except Exception:
            raise RuntimeError("invalid website URL")

        if not ("." in domain and len(domain) > 4):
            raise RuntimeError("could not construct valid email pattern")

        candidates = []

        if person_name:
            clean = person_name.split("@")[0].strip()
            parts = clean.lower().split()
            if len(parts) >= 2:
                first, last = parts[0], parts[-1]
                candidates += [
                    f"{first}@{domain}",
                    f"{first}.{last}@{domain}",
                    f"{first[0]}{last}@{domain}",
                    f"{first}_{last}@{domain}",
                ]
            elif len(parts) == 1:
                candidates.append(f"{parts[0]}@{domain}")

        candidates += [f"{p}@{domain}" for p in _COMMON_EMAIL_PREFIXES]

        return {"email": candidates[0], "phone": None, "linkedin": None}

    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch HTML page content.

        Args:
            url: Page URL

        Returns:
            HTML content or None if fetch fails
        """
        try:
            r = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
            r.raise_for_status()
            return r.text
        except Exception:
            return None

    def _extract_mailto_emails(self, html: str) -> list[str]:
        """Extract emails from mailto: href attributes.

        Args:
            html: HTML content

        Returns:
            List of valid email addresses
        """
        soup = BeautifulSoup(html, "html.parser")
        emails = []
        for a in soup.select("a[href^='mailto:']"):
            email = a["href"].replace("mailto:", "").split("?")[0].strip()
            if self._is_valid_email(email) and not any(
                n in email.lower() for n in _EMAIL_NOISE
            ):
                emails.append(email)
        return emails

    def _extract_text_emails(self, html: str) -> list[str]:
        """Extract emails via regex from page text.

        Args:
            html: HTML content

        Returns:
            List of valid email addresses
        """
        return [
            e
            for e in _EMAIL_RE.findall(html)
            if self._is_valid_email(e) and not any(n in e.lower() for n in _EMAIL_NOISE)
        ]

    def _extract_phones(self, html: str) -> list[str]:
        """Extract phone numbers from HTML.

        Args:
            html: HTML content

        Returns:
            List of normalized phone numbers
        """
        soup = BeautifulSoup(html, "html.parser")
        phones = []

        for a in soup.select("a[href^='tel:']"):
            raw = a["href"].replace("tel:", "").strip()
            phones.append(self._normalize_phone(raw))

        if not phones:
            for m in _PHONE_RE.findall(html):
                phones.append(self._normalize_phone(m))

        return [p for p in phones if p]

    def _is_valid_email(self, email: str) -> bool:
        """Validate email format and reject image filenames.

        Args:
            email: Email address to validate

        Returns:
            True if valid email format
        """
        if not email or "@" not in email:
            return False

        local, domain = email.rsplit("@", 1)
        lower = email.lower()

        if any(
            lower.endswith(ext)
            or (ext in lower and lower.index(ext) < lower.index("@"))
            for ext in _EMAIL_INVALID_EXTENSIONS
        ):
            return False

        if "." not in domain or len(domain) < 4:
            return False

        if "/" in local or " " in local or "\\" in local:
            return False

        return True

    def _normalize_phone(self, raw: str) -> Optional[str]:
        """Normalize Indonesian phone number to +62xxx format.

        Args:
            raw: Raw phone number string

        Returns:
            Normalized phone number or None if invalid
        """
        if self._is_empty(raw):
            return None

        digits = re.sub(r"\D", "", str(raw))
        if not digits:
            return None

        if digits.startswith("08"):
            digits = "62" + digits[1:]
        elif digits.startswith("0"):
            digits = "62" + digits[1:]
        elif not digits.startswith("62"):
            digits = "62" + digits

        return "+" + digits

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
