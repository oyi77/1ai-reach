"""
Prospect pain-point researcher.

For each lead with a website, scrapes their site and builds a research brief:
  - What services they offer
  - What their target market appears to be
  - Visible pain points / gaps (no chatbot, slow site, missing social proof, etc.)
  - Any tech stack signals

Output is stored in data/research/{index}_{name}.txt and a `research` column in leads.csv.
"""

import os
import re
import sys
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

from leads import load_leads, save_leads
from utils import is_empty, parse_display_name, safe_filename

from config import RESEARCH_DIR as _RESEARCH_DIR

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
}
RESEARCH_DIR = str(_RESEARCH_DIR)

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


def _fetch(url: str, timeout: int = 8) -> str | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())[:5000]


def _extract_services(text: str) -> list[str]:
    """Pull service keywords visible on site."""
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
    found = [k for k in keywords if k.lower() in text.lower()]
    return found


def research_prospect(website: str) -> dict:
    if is_empty(website):
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
        html = _fetch(url)
        if html:
            combined_html += html
            combined_text += " " + _clean_text(html)
        if len(combined_text) > 4000:
            break

    if not combined_text.strip():
        return {}

    services = _extract_services(combined_text)
    pain_points = [
        label for label, check in _PAIN_SIGNALS.items() if check(combined_text)
    ]
    tech_stack = [
        name
        for name, signal in _TECH_SIGNALS.items()
        if signal.lower() in combined_html.lower()
    ]

    return {
        "services": services,
        "pain_points": pain_points,
        "tech_stack": tech_stack,
        "text_sample": combined_text[:800],
    }


def format_research_brief(name: str, data: dict) -> str:
    if not data:
        return f"No research data available for {name}."

    pain_labels = {
        "no_chatbot": "No live chat / WhatsApp widget on site",
        "no_blog": "No blog or content section (missing organic SEO leverage)",
        "no_testimonial": "No visible client testimonials or case studies",
        "no_cta": "Weak or missing call-to-action",
        "no_portfolio": "No portfolio / 'our work' section",
    }

    lines = [f"# Prospect Research: {name}"]
    if data.get("services"):
        lines.append(f"Services detected: {', '.join(data['services'])}")
    if data.get("tech_stack"):
        lines.append(f"Tech stack: {', '.join(data['tech_stack'])}")
    if data.get("pain_points"):
        lines.append("Observed gaps/pain points:")
        for p in data["pain_points"]:
            lines.append(f"  - {pain_labels.get(p, p)}")
    return "\n".join(lines)


def process_research() -> None:
    df = load_leads()
    if df is None:
        return

    os.makedirs(RESEARCH_DIR, exist_ok=True)

    if "research" not in df.columns:
        df["research"] = None
    df["research"] = df["research"].astype(object)

    researched = 0
    for index, row in df.iterrows():
        # Skip if already researched
        existing = str(row.get("research") or "")
        if existing and not is_empty(existing):
            continue

        name = parse_display_name(row.get("displayName"))
        website = str(row.get("websiteUri") or "")
        if is_empty(website):
            continue

        print(f"Researching: {name}...")
        data = research_prospect(website)
        brief = format_research_brief(name, data)

        # Save full brief to file
        path = os.path.join(RESEARCH_DIR, f"{index}_{safe_filename(name)}.txt")
        with open(path, "w") as f:
            f.write(brief)

        # Save compact summary to CSV (services + pain points)
        summary_parts = []
        if data.get("services"):
            summary_parts.append("Services: " + ", ".join(data["services"][:4]))
        if data.get("pain_points"):
            summary_parts.append("Gaps: " + ", ".join(data["pain_points"]))
        df.at[index, "research"] = (
            " | ".join(summary_parts) if summary_parts else "no_data"
        )
        researched += 1
        time.sleep(0.5)

    save_leads(df)
    print(f"Research complete. {researched} leads researched.")


if __name__ == "__main__":
    process_research()
