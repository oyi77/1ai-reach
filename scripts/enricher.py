"""
Multi-strategy contact enricher.

Priority order per lead:
  1. AgentCash Minerva    — paid, richest data
  2. Website contact pages — free, scrape /contact /about etc.
  3. Mailto: link scan    — free, most reliable email signal on a page
  4. Common email patterns — free, guess info@/contact@/hello@ and verify
"""
import json
import re
import subprocess
import sys
import time
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from leads import load_leads, save_leads
from utils import parse_display_name

_HEADERS  = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"}
_PHONE_RE = re.compile(r'(?:\+62|(?<!\d)62|08\d)\d{7,11}')
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
_EMAIL_NOISE = {
    "example", "domain", "user@", "test@", "email@", "name@", "your@",
    "noreply@", "no-reply@", "sentry", "wixpress", "squarespace",
    "wordpress", "schema.org", "w3.org", "apple.com", "google.com",
}

# Image/file extensions that should never appear in a valid email
_EMAIL_INVALID_EXTENSIONS = {
    ".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".mp4",
}


def _is_valid_email(email: str) -> bool:
    """Basic sanity check: reject image filenames and other non-email strings."""
    if not email or "@" not in email:
        return False
    local, domain = email.rsplit("@", 1)
    # Reject if local part looks like a file (contains dot + known image ext)
    lower = email.lower()
    if any(lower.endswith(ext) or (ext in lower and lower.index(ext) < lower.index("@")) for ext in _EMAIL_INVALID_EXTENSIONS):
        return False
    # Domain must have a TLD
    if "." not in domain or len(domain) < 4:
        return False
    # Local part should not contain slashes or spaces
    if "/" in local or " " in local or "\\" in local:
        return False
    return True

_CONTACT_PATHS = [
    "/contact", "/contact-us", "/kontak", "/hubungi-kami", "/hubungi",
    "/about", "/tentang-kami", "/about-us", "/reach-us", "/get-in-touch",
]

_COMMON_EMAIL_PREFIXES = ["info", "contact", "hello", "admin", "marketing", "sales", "cs", "halo"]


# ---------------------------------------------------------------------------
# Strategy 1 – AgentCash Minerva (paid)
# ---------------------------------------------------------------------------

def _via_agentcash(website: str, name: str) -> dict:
    result = subprocess.run(
        [
            "npx", "agentcash@latest", "fetch",
            "https://stableenrich.dev/api/minerva/enrich",
            "-m", "POST", "-b", json.dumps({"domain": website, "name": name}),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Check if it's a balance issue — no point retrying
        try:
            err = json.loads(result.stdout)
            if err.get("error", {}).get("cause") == "insufficient_balance":
                raise RuntimeError("AgentCash balance is zero — skipping")
        except (json.JSONDecodeError, AttributeError):
            pass
        raise RuntimeError("non-zero exit")
    data = json.loads(result.stdout)
    person = data.get("data", {}).get("person", {})
    if not person.get("email") and not person.get("phone"):
        raise RuntimeError("no contact info returned")
    return {
        "email":    person.get("email"),
        "phone":    person.get("phone"),
        "linkedin": person.get("linkedin_url"),
    }


# ---------------------------------------------------------------------------
# Strategy 2 & 3 – Website scraping
# ---------------------------------------------------------------------------

def _fetch_page(url: str) -> str | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def _extract_mailto_emails(html: str) -> list[str]:
    """Extract emails from mailto: href attributes — most reliable signal."""
    soup = BeautifulSoup(html, "html.parser")
    emails = []
    for a in soup.select("a[href^='mailto:']"):
        email = a["href"].replace("mailto:", "").split("?")[0].strip()
        if _is_valid_email(email) and not any(n in email.lower() for n in _EMAIL_NOISE):
            emails.append(email)
    return emails


def _extract_text_emails(html: str) -> list[str]:
    """Extract emails via regex from page text."""
    return [
        e for e in _EMAIL_RE.findall(html)
        if _is_valid_email(e) and not any(n in e.lower() for n in _EMAIL_NOISE)
    ]


def _extract_phones(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    # Prefer tel: href
    phones = []
    for a in soup.select("a[href^='tel:']"):
        raw = a["href"].replace("tel:", "").strip()
        phones.append(_normalize_phone(raw))

    if not phones:
        for m in _PHONE_RE.findall(html):
            phones.append(_normalize_phone(m))
    return [p for p in phones if p]


def _normalize_phone(raw: str) -> str | None:
    digits = re.sub(r'\D', '', raw)
    if not digits:
        return None
    if digits.startswith("08"):
        digits = "62" + digits[1:]
    elif not digits.startswith("62"):
        digits = "62" + digits
    return "+" + digits


def _scrape_website(base_url: str) -> dict:
    if not base_url.startswith("http"):
        base_url = "https://" + base_url

    all_emails, all_phones = [], []

    # Try homepage + all contact paths
    pages_to_try = [base_url] + [urljoin(base_url, p) for p in _CONTACT_PATHS]

    for url in pages_to_try:
        html = _fetch_page(url)
        if not html:
            continue
        # mailto: first (most reliable), then regex
        emails = _extract_mailto_emails(html) or _extract_text_emails(html)
        phones = _extract_phones(html)
        all_emails.extend(emails)
        all_phones.extend(phones)
        if all_emails:
            break  # stop as soon as we find emails

    if not all_emails and not all_phones:
        raise RuntimeError("no contact info found on website or contact pages")

    return {
        "email":    all_emails[0] if all_emails else None,
        "phone":    all_phones[0] if all_phones else None,
        "linkedin": None,
    }


# ---------------------------------------------------------------------------
# Strategy 4 – Common email pattern guessing
# ---------------------------------------------------------------------------

def _guess_email(website: str, person_name: str = "") -> dict:
    """Try name-based then common prefix patterns at the business domain."""
    try:
        domain = urlparse(website if website.startswith("http") else "https://" + website).netloc
        domain = domain.lstrip("www.")
    except Exception:
        raise RuntimeError("invalid website URL")

    if not ("." in domain and len(domain) > 4):
        raise RuntimeError("could not construct valid email pattern")

    candidates = []

    # Name-based patterns first (much higher deliverability than info@)
    if person_name:
        # Strip company suffix ("Name @ Company" → "Name")
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

    # Generic business prefixes as fallback
    candidates += [f"{p}@{domain}" for p in _COMMON_EMAIL_PREFIXES]

    return {"email": candidates[0], "phone": None, "linkedin": None}


# ---------------------------------------------------------------------------
# Main enrichment pipeline
# ---------------------------------------------------------------------------

def enrich_lead(website: str, name: str) -> dict | None:
    if not website or str(website).lower() in ("nan", "none", ""):
        return None

    strategies = [
        ("AgentCash Minerva", lambda: _via_agentcash(website, name)),
        ("Website scraping",  lambda: _scrape_website(website)),
        ("Email pattern",     lambda: _guess_email(website, name)),
    ]

    for label, fn in strategies:
        try:
            result = fn()
            if result.get("email") or result.get("phone"):
                print(f"  [{label}] found contact info.")
                return result
        except Exception as e:
            print(f"  [{label}] failed: {e}", file=sys.stderr)

    return None


def process_leads() -> None:
    df = load_leads()
    if df is None:
        return

    for col in ("email", "phone", "linkedin"):
        if col not in df.columns:
            df[col] = None
        df[col] = df[col].astype(object)

    enriched = 0
    for index, row in df.iterrows():
        has_email = pd.notna(row.get("email")) and str(row.get("email")).lower() not in ("nan", "none", "")
        has_phone = pd.notna(row.get("phone")) and str(row.get("phone")).lower() not in ("nan", "none", "")
        if has_email and has_phone:
            continue  # already fully enriched

        name = parse_display_name(row.get("displayName"))
        website = str(row.get("websiteUri", "") or "")
        print(f"Enriching: {name}...")
        info = enrich_lead(website, name)
        if info:
            if not has_email and info.get("email"):
                df.at[index, "email"] = info["email"]
            if not has_phone and info.get("phone"):
                df.at[index, "phone"] = info["phone"]
            if info.get("linkedin"):
                df.at[index, "linkedin"] = info["linkedin"]
            enriched += 1
        time.sleep(0.5)

    save_leads(df)
    print(f"Enrichment complete. {enriched} leads updated.")


if __name__ == "__main__":
    process_leads()
