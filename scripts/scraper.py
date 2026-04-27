"""
Multi-source lead scraper.

Priority order:
  1. Google Places API   — real business data (name, phone, website, type)
  2. Yellow Pages ID     — yellowpages.co.id (free, real Indonesian businesses)
  3. DuckDuckGo          — filtered to skip known aggregator domains
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd

from oneai_reach.application.outreach import ScraperService
from oneai_reach.config.settings import get_settings
from leads import load_leads, save_leads


def search_leads(query: str, city: str = "Jakarta") -> list:
    settings = get_settings()
    service = ScraperService(settings)

    try:
        results = service.search_leads(query, city)
        print(f"Found {len(results)} leads.")
        return results
    except Exception as e:
        print(f"All sources failed: {e}", file=sys.stderr)
        sys.exit(1)


def merge_and_save(new_leads: list) -> None:
    df_new = pd.DataFrame(new_leads)
    df_new["status"] = "new"
    df_old = load_leads()
    if df_old is not None:
        df = pd.concat([df_old, df_new]).drop_duplicates(subset=["id"], keep="last")
    else:
        df = df_new
    save_leads(df)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scraper.py <query> [city]", file=sys.stderr)
        print('  e.g. python3 scraper.py "Coffee Shop" Bandung', file=sys.stderr)
        sys.exit(1)
    query = sys.argv[1]
    city = sys.argv[2] if len(sys.argv) > 2 else "Jakarta"
    leads = search_leads(query, city)
    merge_and_save(leads)
    print(f"Done. {len(leads)} leads saved.")
