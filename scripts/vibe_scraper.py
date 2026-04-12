"""
Vibe Prospecting lead discovery via Claude MCP.

Uses `claude -p --dangerously-skip-permissions` to call the Vibe Prospecting MCP
(fetch-entities + enrich-prospects) and returns decision-maker-level leads.

Merges results into data/leads.csv without overwriting existing leads.
Marks new leads as status="new" with source="vibe_prospecting".
"""

import json
import re
import subprocess
import sys
import time

import pandas as pd

from leads import load_leads, save_leads
from utils import parse_display_name, is_empty, normalize_phone

# How many leads to request per Vibe query
LEADS_PER_QUERY = 20

_PROMPT_TEMPLATE = """\
Using Vibe Prospecting, find {n} {industry} businesses in {location}.
For each one, find the top decision maker (CEO, CMO, Marketing Director, or Owner).
Return ONLY a valid JSON array — no markdown, no explanation, nothing else.
Each object must have exactly these keys:
  company, website, decision_maker_name, decision_maker_title, email, linkedin, address, phone
Use empty string "" for any field you cannot find. Example:
[{{"company":"Acme","website":"acme.com","decision_maker_name":"Jane","decision_maker_title":"CEO","email":"jane@acme.com","linkedin":"linkedin.com/in/jane","address":"Jakarta","phone":"+62811000000"}}]
"""


def _call_vibe(industry: str, location: str, n: int = LEADS_PER_QUERY) -> list[dict]:
    prompt = _PROMPT_TEMPLATE.format(n=n, industry=industry, location=location)
    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--output-format",
                "text",
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = result.stdout.strip()
        if not output:
            print(
                f"Vibe returned empty output. stderr: {result.stderr[:300]}",
                file=sys.stderr,
            )
            return []

        # Extract JSON array from output (may be wrapped in ```json ... ```)
        json_match = re.search(r"\[.*\]", output, re.DOTALL)
        if not json_match:
            print(
                f"Could not find JSON array in Vibe output:\n{output[:500]}",
                file=sys.stderr,
            )
            return []

        data = json.loads(json_match.group(0))
        if isinstance(data, list):
            return data
        return []

    except subprocess.TimeoutExpired:
        print("Vibe query timed out (180s).", file=sys.stderr)
        return []
    except json.JSONDecodeError as e:
        print(f"Failed to parse Vibe JSON: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Vibe scraper error: {e}", file=sys.stderr)
        return []


def _to_display_name(name: str) -> str:
    """Wrap name in the dict format used by the rest of the pipeline."""
    return json.dumps({"text": name})


def vibe_scrape(
    industry: str, location: str = "Jakarta, Indonesia", n: int = LEADS_PER_QUERY
) -> None:
    print(f"\nVibe Prospecting: searching {n} '{industry}' leads in {location}...")

    raw_leads = _call_vibe(industry, location, n)
    if not raw_leads:
        print("No leads returned from Vibe.")
        return

    print(f"  Got {len(raw_leads)} raw leads from Vibe.")

    df = load_leads()
    if df is None:
        df = pd.DataFrame()

    # Build a set of existing websites + emails to deduplicate
    existing_sites = set()
    existing_emails = set()
    if not df.empty:
        for val in df.get("websiteUri", pd.Series()).dropna():
            s = (
                str(val)
                .strip()
                .lower()
                .rstrip("/")
                .replace("https://", "")
                .replace("http://", "")
                .replace("www.", "")
            )
            if not is_empty(s):
                existing_sites.add(s)
        for val in df.get("email", pd.Series()).dropna():
            e = str(val).strip().lower()
            if not is_empty(e):
                existing_emails.add(e)

    new_rows = []
    skipped = 0

    for lead in raw_leads:
        company = str(lead.get("company") or "").strip()
        website = str(lead.get("website") or "").strip()
        dm_name = str(lead.get("decision_maker_name") or "").strip()
        dm_title = str(lead.get("decision_maker_title") or "").strip()
        email = str(lead.get("email") or "").strip()
        linkedin = str(lead.get("linkedin") or "").strip()
        address = str(lead.get("address") or "").strip()
        phone = normalize_phone(str(lead.get("phone") or "")) or ""

        if not company:
            skipped += 1
            continue

        # Dedup by website or email
        site_key = (
            website.lower()
            .rstrip("/")
            .replace("https://", "")
            .replace("http://", "")
            .replace("www.", "")
        )
        if site_key and site_key in existing_sites:
            print(f"  [skip] {company} — already in leads (website match).")
            skipped += 1
            continue
        if email and email.lower() in existing_emails:
            print(f"  [skip] {company} — already in leads (email match).")
            skipped += 1
            continue

        # Build display name: "Decision Maker @ Company" or just Company
        if dm_name:
            display = f"{dm_name} @ {company}"
        else:
            display = company

        row = {
            "id": f"vibe_{re.sub(r'[^a-z0-9]', '', company.lower()[:20])}_{int(time.time())}",
            "displayName": _to_display_name(display),
            "formattedAddress": address,
            "internationalPhoneNumber": phone,
            "phone": phone,
            "websiteUri": website
            if website.startswith("http")
            else (f"https://{website}" if website else ""),
            "primaryType": "service",
            "type": "Layanan",
            "source": "vibe_prospecting",
            "status": "new",
            "email": email,
            "linkedin": linkedin,
            "contacted_at": None,
            "followup_at": None,
            "replied_at": None,
            "research": f"Decision maker: {dm_name} ({dm_title})" if dm_name else "",
            "review_score": None,
            "review_issues": None,
        }

        new_rows.append(row)
        if site_key:
            existing_sites.add(site_key)
        if email:
            existing_emails.add(email.lower())

        print(f"  + {company} — {dm_name} ({dm_title}) {email}")

    if not new_rows:
        print(f"No new leads to add (all {skipped} were duplicates).")
        return

    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([df, new_df], ignore_index=True) if not df.empty else new_df
    save_leads(combined)
    print(
        f"\nVibe scrape complete: {len(new_rows)} new leads added, {skipped} skipped."
    )


if __name__ == "__main__":
    # Usage: python3 vibe_scraper.py "Digital Agency" "Jakarta, Indonesia" 20
    args = sys.argv[1:]
    industry = args[0] if len(args) > 0 else "Digital Marketing Agency"
    location = args[1] if len(args) > 1 else "Jakarta, Indonesia"
    count = int(args[2]) if len(args) > 2 else LEADS_PER_QUERY
    vibe_scrape(industry, location, count)
