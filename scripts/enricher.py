"""
Multi-strategy contact enricher.

Priority order per lead:
  1. AgentCash Minerva    — paid, richest data
  2. Website contact pages — free, scrape /contact /about etc.
  3. Mailto: link scan    — free, most reliable email signal on a page
  4. Common email patterns — free, guess info@/contact@/hello@ and verify
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.outreach import EnricherService
from oneai_reach.config.settings import get_settings
from leads import load_leads, save_leads
from utils import parse_display_name, is_empty


def process_leads() -> None:
    settings = get_settings()
    service = EnricherService(settings)

    df = load_leads()
    if df is None:
        return

    for col in ("email", "phone", "linkedin"):
        if col not in df.columns:
            df[col] = None
        df[col] = df[col].astype(object)

    enriched = 0
    for index, row in df.iterrows():
        has_email = not is_empty(row.get("email"))
        has_phone = not is_empty(row.get("phone"))
        if has_email and has_phone:
            continue

        name = parse_display_name(row.get("displayName"))
        website = str(row.get("websiteUri", "") or "")
        print(f"Enriching: {name}...")
        info = service.enrich_lead(website, name)
        if info:
            if not has_email and info.get("email"):
                df.at[index, "email"] = info["email"]
            if not has_phone and info.get("phone"):
                df.at[index, "phone"] = info["phone"]
            if info.get("linkedin"):
                df.at[index, "linkedin"] = info["linkedin"]
            enriched += 1
            if str(df.at[index, "status"] or "") in ("new", ""):
                df.at[index, "status"] = "enriched"
        time.sleep(0.5)

    save_leads(df)
    print(f"Enrichment complete. {enriched} leads updated.")


if __name__ == "__main__":
    process_leads()
