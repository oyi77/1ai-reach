"""
Prospect pain-point researcher.

For each lead with a website, scrapes their site and builds a research brief:
  - What services they offer
  - What their target market appears to be
  - Visible pain points / gaps (no chatbot, slow site, missing social proof, etc.)
  - Any tech stack signals

Output is stored in data/research/{index}_{name}.txt and a `research` column in leads.csv.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.outreach import ResearcherService
from oneai_reach.config.settings import get_settings
from leads import load_leads, save_leads
from utils import is_empty, parse_display_name, safe_filename


def process_research() -> None:
    settings = get_settings()
    service = ResearcherService(settings)

    df = load_leads()
    if df is None:
        return

    if "research" not in df.columns:
        df["research"] = None
    df["research"] = df["research"].astype(object)

    researched = 0
    for index, row in df.iterrows():
        existing = str(row.get("research") or "")
        if existing and not is_empty(existing):
            continue

        name = parse_display_name(row.get("displayName"))
        website = str(row.get("websiteUri") or "")
        if is_empty(website):
            continue

        print(f"Researching: {name}...")
        data = service.research_prospect(website)
        brief = service.format_research_brief(name, data)
        service.save_research_brief(index, name, brief)

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
