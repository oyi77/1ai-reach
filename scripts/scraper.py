"""
Multi-source lead scraper.

Priority order:
  1. Google Places API   — real business data (name, phone, website, type)
  2. Yellow Pages ID     — yellowpages.co.id (free, real Indonesian businesses)
  3. DuckDuckGo          — filtered to skip known aggregator domains
"""

import sys
import time
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import GOOGLE_API_KEY, AGGREGATOR_DOMAINS
from leads import load_leads, save_leads

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
}

# ---------------------------------------------------------------------------
# Source 1 – Google Places API (new v1)
# ---------------------------------------------------------------------------


def search_google_places(query: str, max_pages: int = 3) -> list:
    """Fetch real business listings from Google Places API (new v1)."""
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY not set")

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        **_HEADERS,
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.internationalPhoneNumber,places.nationalPhoneNumber,"
            "places.websiteUri,places.primaryType,places.primaryTypeDisplayName,"
            "nextPageToken"
        ),
        "Content-Type": "application/json",
    }

    leads, page_token = [], None
    for _ in range(max_pages):
        body = {"textQuery": query, "languageCode": "id", "maxResultCount": 20}
        if page_token:
            body["pageToken"] = page_token

        resp = requests.post(url, json=body, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        for p in data.get("places", []):
            leads.append(
                {
                    "id": p.get("id"),
                    "displayName": p.get("displayName", {}).get("text"),
                    "formattedAddress": p.get("formattedAddress"),
                    "internationalPhoneNumber": p.get("internationalPhoneNumber"),
                    "phone": p.get("nationalPhoneNumber"),
                    "websiteUri": p.get("websiteUri"),
                    "primaryType": p.get("primaryType"),
                    "type": p.get("primaryTypeDisplayName", {}).get("text"),
                    "source": "google_places",
                }
            )

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)  # respect rate limits between pages

    return leads


# ---------------------------------------------------------------------------
# Source 2 – Yellow Pages Indonesia
# ---------------------------------------------------------------------------


def _yp_clean_text(el) -> str:
    return el.get_text(strip=True) if el else ""


def search_yellowpages(query: str, city: str = "jakarta") -> list:
    """Scrape yellowpages.co.id for Indonesian business listings."""
    slug = query.lower().replace(" ", "-")
    url = f"https://www.yellowpages.co.id/cari/{slug}/{city}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        # Try alternative URL pattern
        url = f"https://www.yellowpages.co.id/search?type=business&term={query.replace(' ', '+')}&location={city}"
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    leads = []

    for card in soup.select(
        ".listing-item, .business-listing, .result-item, article.listing"
    ):
        name_el = card.select_one("h2, h3, .listing-name, .business-name")
        phone_el = card.select_one(".phone, .tel, [href^='tel:']")
        web_el = card.select_one(
            "a.website, a[href^='http']:not([href*='yellowpages'])"
        )

        name = _yp_clean_text(name_el)
        phone = _yp_clean_text(phone_el) or (
            phone_el.get("href", "").replace("tel:", "") if phone_el else None
        )
        website = web_el.get("href") if web_el else None

        if not name:
            continue

        leads.append(
            {
                "id": f"yp_{abs(hash(name + str(website))) % 999999}",
                "displayName": name,
                "formattedAddress": _yp_clean_text(
                    card.select_one(".address, .location")
                ),
                "internationalPhoneNumber": phone,
                "phone": phone,
                "websiteUri": website,
                "primaryType": query,
                "type": query,
                "source": "yellowpages_id",
            }
        )

    if not leads:
        raise RuntimeError(f"Yellow Pages returned 0 results for '{query}' in {city}")
    return leads


# ---------------------------------------------------------------------------
# Source 3 – DuckDuckGo (filtered)
# ---------------------------------------------------------------------------


def _is_real_business(url: str) -> bool:
    """Return True if the URL looks like a real business site, not a directory."""
    if not url:
        return False
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return False
    if any(domain == agg or domain.endswith("." + agg) for agg in AGGREGATOR_DOMAINS):
        return False
    # Skip generic top-level sites that are clearly not a business page
    generic = {"google.com", "bing.com", "yahoo.com", "duckduckgo.com"}
    return domain not in generic


def search_duckduckgo(query: str) -> list:
    """Scrape DuckDuckGo HTML, filtering out directories and aggregators."""
    resp = requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers=_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    leads = []

    for idx, result in enumerate(soup.select(".result")):
        title_el = result.select_one(".result__title")
        url_el = result.select_one(".result__url")
        if not title_el or not url_el:
            continue

        name = title_el.get_text(strip=True)
        website = url_el.get_text(strip=True).strip()
        if not website.startswith("http"):
            website = "https://" + website

        if not _is_real_business(website):
            continue

        leads.append(
            {
                "id": f"ddg_{abs(hash(website)) % 999999}",
                "displayName": name,
                "formattedAddress": None,
                "internationalPhoneNumber": None,
                "phone": None,
                "websiteUri": website,
                "primaryType": None,
                "type": None,
                "source": "duckduckgo",
            }
        )

        if len(leads) >= 10:
            break

    if not leads:
        raise RuntimeError("DuckDuckGo returned 0 real business results")
    return leads


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def search_leads(query: str, city: str = "Jakarta") -> list:
    full_query = f"{query} in {city}" if city.lower() not in query.lower() else query
    print(f"Searching: {full_query}")

    for source_name, fn in [
        ("Google Places", lambda: search_google_places(full_query)),
        ("Yellow Pages ID", lambda: search_yellowpages(query, city.lower())),
        ("DuckDuckGo", lambda: search_duckduckgo(full_query)),
    ]:
        try:
            results = fn()
            print(f"  [{source_name}] found {len(results)} leads.")
            return results
        except Exception as e:
            print(f"  [{source_name}] failed: {e}", file=sys.stderr)

    print("All sources failed. No leads found.", file=sys.stderr)
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
