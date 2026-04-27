"""Lead scraper service - extracts business logic from scripts/scraper.py."""

import time
from typing import List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError, MissingConfigurationError
from oneai_reach.domain.models import Lead, LeadStatus
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
}


class ScraperService:
    """Service for scraping leads from multiple sources.

    Priority order:
      1. Google Places API - real business data
      2. Yellow Pages ID - yellowpages.co.id
      3. DuckDuckGo - filtered to skip aggregators
    """

    def __init__(self, config: Settings):
        """Initialize scraper service.

        Args:
            config: Application settings
        """
        self.config = config
        self.google_api_key = config.external_api.google_api_key
        self.aggregator_domains = config.scraper.aggregator_domains

    def search_leads(self, query: str, city: str = "Jakarta") -> List[dict]:
        """Search for leads using multiple sources with fallback.

        Args:
            query: Search query (e.g., "Coffee Shop")
            city: City name for location-based search

        Returns:
            List of lead dictionaries

        Raises:
            ExternalAPIError: If all sources fail
        """
        full_query = (
            f"{query} in {city}" if city.lower() not in query.lower() else query
        )
        logger.info(f"Searching leads: {full_query}")

        sources = [
            ("Semantic Intent Search", lambda: self._search_semantic_intent(full_query)),
            ("Google Places", lambda: self._search_google_places(full_query)),
            ("Yellow Pages ID", lambda: self._search_yellowpages(query, city.lower())),
            ("DuckDuckGo", lambda: self._search_duckduckgo(full_query)),
        ]

        for source_name, fn in sources:
            try:
                results = fn()
                logger.info(f"[{source_name}] found {len(results)} leads")
                return results
            except Exception as e:
                logger.warning(f"[{source_name}] failed: {e}")

        raise ExternalAPIError(
            service="all_scrapers",
            endpoint="/search",
            status_code=0,
            reason="All scraping sources failed",
        )

    def _search_semantic_intent(self, query: str) -> List[dict]:
        """Fetch leads using Exa or DuckDuckGo semantic intent search."""
        import asyncio
        from oneai_reach.infrastructure.semantic_search import search_leads_by_intent
        
        api_key = getattr(self.config.external_api, 'exa_api_key', None)
        
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
            results = run_async(search_leads_by_intent(query, api_key))
        else:
            results = loop.run_until_complete(search_leads_by_intent(query, api_key))
            
        leads = []
        for res in results:
            if not res.get("website"):
                continue
            leads.append(
                {
                    "id": f"sem_{abs(hash(res.get('website', ''))) % 999999}",
                    "displayName": res.get("text", "Unknown Business"),
                    "formattedAddress": None,
                    "internationalPhoneNumber": None,
                    "phone": None,
                    "websiteUri": res.get("website"),
                    "primaryType": query,
                    "type": query,
                    "source": "semantic_intent",
                }
            )

        if not leads:
            raise ExternalAPIError(
                service="semantic_search",
                endpoint="/search",
                status_code=200,
                reason=f"No results found for '{query}'",
            )
        return leads

    def _search_google_places(self, query: str, max_pages: int = 3) -> List[dict]:
        """Fetch leads from Google Places API (new v1).

        Args:
            query: Search query
            max_pages: Maximum number of pages to fetch

        Returns:
            List of lead dictionaries

        Raises:
            MissingConfigurationError: If API key not configured
            ExternalAPIError: If API call fails
        """
        if not self.google_api_key:
            raise MissingConfigurationError(
                config_key="GOOGLE_API_KEY", reason="Required for Google Places API"
            )

        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            **_HEADERS,
            "X-Goog-Api-Key": self.google_api_key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.internationalPhoneNumber,places.nationalPhoneNumber,"
                "places.websiteUri,places.primaryType,places.primaryTypeDisplayName,"
                "nextPageToken"
            ),
            "Content-Type": "application/json",
        }

        leads = []
        page_token = None

        for _ in range(max_pages):
            body = {"textQuery": query, "languageCode": "id", "maxResultCount": 20}
            if page_token:
                body["pageToken"] = page_token

            try:
                resp = requests.post(url, json=body, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                raise ExternalAPIError(
                    service="google_places",
                    endpoint="/v1/places:searchText",
                    status_code=getattr(e.response, "status_code", 0)
                    if hasattr(e, "response")
                    else 0,
                    reason=str(e),
                )

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
            time.sleep(2)  # Rate limit respect

        return leads

    def _search_yellowpages(self, query: str, city: str = "jakarta") -> List[dict]:
        """Scrape yellowpages.co.id for Indonesian business listings.

        Args:
            query: Search query
            city: City name

        Returns:
            List of lead dictionaries

        Raises:
            ExternalAPIError: If scraping fails
        """
        slug = query.lower().replace(" ", "-")
        url = f"https://www.yellowpages.co.id/cari/{slug}/{city}"

        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception:
            # Try alternative URL pattern
            url = f"https://www.yellowpages.co.id/search?type=business&term={query.replace(' ', '+')}&location={city}"
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                raise ExternalAPIError(
                    service="yellowpages_id",
                    endpoint=url,
                    status_code=getattr(e.response, "status_code", 0)
                    if hasattr(e, "response")
                    else 0,
                    reason=str(e),
                )

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

            name = self._clean_text(name_el)
            phone = self._clean_text(phone_el) or (
                phone_el.get("href", "").replace("tel:", "") if phone_el else None
            )
            website = web_el.get("href") if web_el else None

            if not name:
                continue

            leads.append(
                {
                    "id": f"yp_{abs(hash(name + str(website))) % 999999}",
                    "displayName": name,
                    "formattedAddress": self._clean_text(
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
            raise ExternalAPIError(
                service="yellowpages_id",
                endpoint=url,
                status_code=200,
                reason=f"No results found for '{query}' in {city}",
            )

        return leads

    def _search_duckduckgo(self, query: str) -> List[dict]:
        """Scrape DuckDuckGo HTML, filtering out directories and aggregators.

        Args:
            query: Search query

        Returns:
            List of lead dictionaries

        Raises:
            ExternalAPIError: If scraping fails
        """
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise ExternalAPIError(
                service="duckduckgo",
                endpoint="/html/",
                status_code=getattr(e.response, "status_code", 0)
                if hasattr(e, "response")
                else 0,
                reason=str(e),
            )

        soup = BeautifulSoup(resp.text, "html.parser")
        leads = []

        for result in soup.select(".result"):
            title_el = result.select_one(".result__title")
            url_el = result.select_one(".result__url")
            if not title_el or not url_el:
                continue

            name = title_el.get_text(strip=True)
            website = url_el.get_text(strip=True).strip()
            if not website.startswith("http"):
                website = "https://" + website

            if not self._is_real_business(website):
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
            raise ExternalAPIError(
                service="duckduckgo",
                endpoint="/html/",
                status_code=200,
                reason="No real business results found",
            )

        return leads

    def _is_real_business(self, url: str) -> bool:
        """Check if URL is a real business site, not a directory.

        Args:
            url: Website URL

        Returns:
            True if real business, False if aggregator/directory
        """
        if not url:
            return False

        try:
            domain = urlparse(url).netloc.lower().lstrip("www.")
        except Exception:
            return False

        if any(
            domain == agg or domain.endswith("." + agg)
            for agg in self.aggregator_domains
        ):
            return False

        # Skip generic top-level sites
        generic = {"google.com", "bing.com", "yahoo.com", "duckduckgo.com"}
        return domain not in generic

    @staticmethod
    def _clean_text(el) -> str:
        """Extract clean text from BeautifulSoup element.

        Args:
            el: BeautifulSoup element

        Returns:
            Cleaned text string
        """
        return el.get_text(strip=True) if el else ""
