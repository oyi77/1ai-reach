import time
from functools import wraps
from typing import Any, Callable, List, Optional

import requests

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import (
    APIRateLimitError,
    APITimeoutError,
    ExternalAPIError,
)


def retry_with_backoff(max_retries: int = 3, backoff_factor: float = 1.0) -> Callable:
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
    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: List[float] = []

    def is_allowed(self) -> bool:
        now = time.time()
        self.requests = [r for r in self.requests if r > now - self.window_seconds]

        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False

    def wait_time(self) -> float:
        if not self.requests:
            return 0.0

        now = time.time()
        self.requests = [r for r in self.requests if r > now - self.window_seconds]

        if len(self.requests) < self.max_requests:
            return 0.0

        oldest = min(self.requests)
        return max(0.0, (oldest + self.window_seconds) - now)


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.external_api.google_api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.timeout = 60
        self.rate_limiter = RateLimiter(max_requests=60, window_seconds=60)

    def _check_rate_limit(self) -> None:
        if not self.rate_limiter.is_allowed():
            wait_time = self.rate_limiter.wait_time()
            raise APIRateLimitError(
                service="gemini",
                limit=self.rate_limiter.max_requests,
                window_seconds=self.rate_limiter.window_seconds,
                retry_after_seconds=int(wait_time) + 1,
            )

    @retry_with_backoff(max_retries=3, backoff_factor=1.0)
    def generate(
        self,
        prompt: str,
        model: str = "gemini-1.5-flash",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> Optional[str]:
        if not self.api_key:
            return None

        self._check_rate_limit()

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )

            if response.status_code == 200:
                data = response.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    candidate = data["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        parts = candidate["content"]["parts"]
                        if len(parts) > 0 and "text" in parts[0]:
                            return parts[0]["text"]
                return None

            raise ExternalAPIError(
                service="gemini",
                endpoint=f"/models/{model}:generateContent",
                status_code=response.status_code,
                reason=response.text[:200],
            )

        except requests.Timeout:
            raise APITimeoutError(
                service="gemini",
                endpoint=f"/models/{model}:generateContent",
                timeout_seconds=self.timeout,
            )
        except ExternalAPIError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                service="gemini",
                endpoint=f"/models/{model}:generateContent",
                status_code=0,
                reason=str(e),
            )
