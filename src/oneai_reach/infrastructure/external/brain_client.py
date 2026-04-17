"""BerkahKarya Hub Brain API client.

Connects to the hub's /brain/* API (FastAPI, port 9099) to:
  - Store outreach learnings (what proposals got replies, what verticals convert)
  - Query past strategy before generating proposals
  - Sync pipeline outcomes for all hub agents to learn from

Includes retry logic, rate limiting, and proper error handling.
"""

import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

import requests

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import (
    APIRateLimitError,
    APITimeoutError,
    ExternalAPIError,
)


def retry_with_backoff(max_retries: int = 3, backoff_factor: float = 1.0) -> Callable:
    """Decorator for retrying failed API calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_factor: Base delay multiplier in seconds (default: 1.0)
                       Delays: 1s, 2s, 4s for backoff_factor=1.0

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, ExternalAPIError) as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = backoff_factor * (2**attempt)
                    time.sleep(delay)
            return None

        return wrapper

    return decorator


class RateLimiter:
    """Simple rate limiter using sliding window algorithm.

    Tracks request timestamps and enforces rate limits per time window.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in the time window
            window_seconds: Time window duration in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: List[float] = []

    def is_allowed(self) -> bool:
        """Check if a request is allowed under current rate limit.

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        now = time.time()
        # Remove requests outside the current window
        self.requests = [r for r in self.requests if r > now - self.window_seconds]

        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False

    def wait_time(self) -> float:
        """Calculate seconds to wait before next request is allowed.

        Returns:
            Seconds to wait (0 if request is allowed now)
        """
        if not self.requests:
            return 0.0

        now = time.time()
        self.requests = [r for r in self.requests if r > now - self.window_seconds]

        if len(self.requests) < self.max_requests:
            return 0.0

        oldest = min(self.requests)
        return max(0.0, (oldest + self.window_seconds) - now)


class BrainClient:
    """Client for BerkahKarya Hub Brain API.

    Provides methods to search, add, and query the shared brain for
    outreach intelligence and learnings.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize Brain client with settings.

        Args:
            settings: Application settings containing hub configuration
        """
        self.base_url = settings.hub.url.rstrip("/")
        self.api_key = settings.hub.api_key
        self.timeout = 15  # seconds for search/add calls
        self.timeout_fast = 3  # seconds for health checks
        self.rate_limiter = RateLimiter(max_requests=30, window_seconds=60)

    def _headers(self) -> Dict[str, str]:
        """Build request headers with API key if configured.

        Returns:
            Dictionary of HTTP headers
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    def _check_rate_limit(self) -> None:
        """Check rate limit and raise exception if exceeded.

        Raises:
            APIRateLimitError: If rate limit is exceeded
        """
        if not self.rate_limiter.is_allowed():
            wait_time = self.rate_limiter.wait_time()
            raise APIRateLimitError(
                service="brain",
                limit=self.rate_limiter.max_requests,
                window_seconds=self.rate_limiter.window_seconds,
                retry_after_seconds=int(wait_time) + 1,
            )

    @retry_with_backoff(max_retries=3, backoff_factor=1.0)
    def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict]:
        """Execute GET request with retry logic.

        Args:
            path: API endpoint path
            params: Query parameters

        Returns:
            Response JSON as dictionary, or None on failure

        Raises:
            ExternalAPIError: On API error response
            APITimeoutError: On request timeout
        """
        self._check_rate_limit()

        try:
            response = requests.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            raise APITimeoutError(
                service="brain", endpoint=path, timeout_seconds=self.timeout
            )
        except requests.HTTPError as e:
            raise ExternalAPIError(
                service="brain",
                endpoint=path,
                status_code=e.response.status_code if e.response else 0,
                reason=str(e),
            )
        except Exception as e:
            raise ExternalAPIError(
                service="brain", endpoint=path, status_code=0, reason=str(e)
            )

    @retry_with_backoff(max_retries=3, backoff_factor=1.0)
    def _post(self, path: str, data: Dict[str, Any]) -> Optional[Dict]:
        """Execute POST request with retry logic.

        Args:
            path: API endpoint path
            data: Request body data

        Returns:
            Response JSON as dictionary, or None on failure

        Raises:
            ExternalAPIError: On API error response
            APITimeoutError: On request timeout
        """
        self._check_rate_limit()

        try:
            response = requests.post(
                f"{self.base_url}{path}",
                json=data,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            raise APITimeoutError(
                service="brain", endpoint=path, timeout_seconds=self.timeout
            )
        except requests.HTTPError as e:
            raise ExternalAPIError(
                service="brain",
                endpoint=path,
                status_code=e.response.status_code if e.response else 0,
                reason=str(e),
            )
        except Exception as e:
            raise ExternalAPIError(
                service="brain", endpoint=path, status_code=0, reason=str(e)
            )

    def search(
        self, query: str, limit: int = 3, method: str = "hybrid"
    ) -> List[Dict[str, Any]]:
        """Search brain for relevant memories.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            method: Search method (hybrid, semantic, keyword)

        Returns:
            List of memory dictionaries with content, score, category
        """
        try:
            result = self._get(
                "/brain/search", {"query": query, "limit": limit, "method": method}
            )
            if result and isinstance(result, list):
                return result
            if result and isinstance(result, dict):
                return result.get("results", [])
            return []
        except Exception:
            # Fail silently - brain is optional
            return []

    def add(
        self, content: str, category: str = "outreach", agent_id: str = "1ai-reach"
    ) -> Optional[str]:
        """Add a memory to the shared brain.

        Args:
            content: Memory content to store
            category: Memory category (outreach, outreach_win, outreach_loss)
            agent_id: Agent identifier

        Returns:
            Memory ID if successful, None otherwise
        """
        try:
            result = self._post(
                "/brain/add",
                {
                    "content": content,
                    "category": category,
                    "agent_id": agent_id,
                    "metadata": {
                        "source": "1ai-reach",
                        "ts": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )
            if result:
                return result.get("id") or result.get("memory_id")
            return None
        except Exception:
            # Fail silently - brain is optional
            return None

    def get_strategy(self, vertical: str, location: str = "Jakarta") -> str:
        """Query brain for outreach strategies that worked in this vertical.

        Args:
            vertical: Business vertical (e.g., "Coffee Shop", "Digital Agency")
            location: Location filter

        Returns:
            Formatted string with past intelligence, or empty string if none found
        """
        query = f"successful outreach proposal {vertical} {location} reply conversion"
        results = self.search(query, limit=3)
        if not results:
            return ""

        lines = []
        for r in results:
            content = r.get("content", "").strip()
            if content:
                lines.append(f"- {content[:200]}")
        if not lines:
            return ""
        return "Past outreach intelligence from our brain:\n" + "\n".join(lines)

    def learn_outcome(
        self,
        lead_name: str,
        vertical: str,
        status: str,
        pain_points: str = "",
        review_score: str = "",
        decision_maker: str = "",
    ) -> None:
        """Store an outreach outcome in the brain for future learning.

        Args:
            lead_name: Name of the lead
            vertical: Business vertical
            status: Outcome status (replied, won, lost, cold, contacted)
            pain_points: Pain points addressed in outreach
            review_score: Proposal quality score
            decision_maker: Decision maker name
        """
        # Only store meaningful outcomes
        if status not in ("replied", "won", "lost", "cold", "contacted"):
            return

        outcome_map = {
            "replied": "got a reply",
            "won": "converted to a deal",
            "lost": "did not convert (lost)",
            "cold": "went cold (no response after follow-up)",
            "contacted": "was contacted",
        }
        outcome = outcome_map.get(status, status)

        parts = [f"Outreach to {lead_name} ({vertical}) {outcome}."]
        if decision_maker:
            parts.append(f"Decision maker: {decision_maker}.")
        if pain_points:
            parts.append(f"Pain points addressed: {pain_points}.")
        if review_score:
            parts.append(f"Proposal score: {review_score}/10.")

        content = " ".join(parts)
        category = "outreach_win" if status in ("replied", "won") else "outreach_loss"
        self.add(content, category=category)

    def stats(self) -> Optional[Dict[str, Any]]:
        """Get brain statistics (total memories, by category).

        Returns:
            Statistics dictionary, or None on failure
        """
        try:
            return self._get("/brain/stats")
        except Exception:
            return None

    def is_online(self) -> bool:
        """Quick health check to verify hub brain is reachable.

        Returns:
            True if brain is online, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/health",
                headers=self._headers(),
                timeout=self.timeout_fast,
            )
            return response.status_code < 300
        except Exception:
            return False
