import sys
import time
import csv
import io
from typing import Optional

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from config import GMAPS_SCRAPER_URL


class GmapsScraperClient:
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or GMAPS_SCRAPER_URL).rstrip("/")
        self.timeout = 30

    def create_job(self, query: str, max_results: int = 50) -> Optional[str]:
        if not _HAS_REQUESTS:
            print("[gmaps_client] requests not installed", file=sys.stderr)
            return None
        try:
            r = requests.post(
                f"{self.base_url}/api/v1/jobs",
                json={
                    "name": f"1ai-reach-{int(time.time())}",
                    "keywords": [query],
                    "max": max_results,
                    "lang": "id",
                    "depth": 1,
                    "max_time": 120,
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("id")
        except Exception as e:
            print(f"[gmaps_client] create_job failed: {e}", file=sys.stderr)
            return None

    def poll_job(self, job_id: str, timeout: int = 180, interval: int = 5) -> Optional[dict]:
        if not _HAS_REQUESTS:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(
                    f"{self.base_url}/api/v1/jobs/{job_id}",
                    timeout=self.timeout,
                )
                r.raise_for_status()
                data = r.json()
                status = data.get("Status", "")
                if status in ("ok", "done", "error"):
                    return data
            except Exception as e:
                print(f"[gmaps_client] poll error: {e}", file=sys.stderr)
            time.sleep(interval)
        print(f"[gmaps_client] poll timeout for job {job_id}", file=sys.stderr)
        return None

    def download_results(self, job_id: str) -> list[dict]:
        if not _HAS_REQUESTS:
            return []
        try:
            r = requests.get(
                f"{self.base_url}/api/v1/jobs/{job_id}/download",
                timeout=self.timeout,
            )
            r.raise_for_status()
            text = r.text.strip()
            if not text:
                return []
            reader = csv.DictReader(io.StringIO(text))
            return [row for row in reader if row.get("title")]
        except Exception as e:
            print(f"[gmaps_client] download failed: {e}", file=sys.stderr)
            return []

    def scrape(self, query: str, max_results: int = 50) -> list[dict]:
        job_id = self.create_job(query, max_results)
        if not job_id:
            print("[gmaps_client] scrape: could not create job", file=sys.stderr)
            return []
        print(f"[gmaps_client] job {job_id} created for '{query}'")
        status = self.poll_job(job_id)
        if not status or status.get("Status") != "ok":
            print(f"[gmaps_client] scrape: job did not complete (status={status})", file=sys.stderr)
            return []
        raw_results = self.download_results(job_id)
        print(f"[gmaps_client] got {len(raw_results)} raw results")
        mapped = [self.map_to_lead(r) for r in raw_results]
        return [m for m in mapped if m.get("id")]

    @staticmethod
    def map_to_lead(raw: dict) -> dict:
        place_id = raw.get("place_id", "") or raw.get("google_id", "") or raw.get("cid", "") or ""
        title = raw.get("title", "")
        review_count = raw.get("review_count", "0")
        review_rating = raw.get("review_rating", "0")
        try:
            review_count = int(review_count) if review_count else 0
        except (ValueError, TypeError):
            review_count = 0
        try:
            review_rating = float(review_rating) if review_rating else 0.0
        except (ValueError, TypeError):
            review_rating = 0.0
        return {
            "id": place_id,
            "displayName": title,
            "formattedAddress": raw.get("address", ""),
            "phone": raw.get("phone", ""),
            "websiteUri": raw.get("website", ""),
            "email": raw.get("email", ""),
            "primaryType": raw.get("category", ""),
            "type": raw.get("category", ""),
            "rating": review_rating,
            "reviewCount": review_count,
            "latitude": raw.get("latitude", 0),
            "longitude": raw.get("longitude", 0),
            "source": "gmaps_scraper",
            "status": "new",
        }
