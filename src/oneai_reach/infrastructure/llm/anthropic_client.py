import os
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


class AnthropicClient:
    def __init__(self, settings: Settings) -> None:
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = "https://api.anthropic.com/v1"
        self.timeout = 60
        self.rate_limiter = RateLimiter(max_requests=50, window_seconds=60)

    def _check_rate_limit(self) -> None:
        if not self.rate_limiter.is_allowed():
            wait_time = self.rate_limiter.wait_time()
            raise APIRateLimitError(
                service="anthropic",
                limit=self.rate_limiter.max_requests,
                window_seconds=self.rate_limiter.window_seconds,
                retry_after_seconds=int(wait_time) + 1,
            )

    @retry_with_backoff(max_retries=3, backoff_factor=1.0)
    def generate(
        self,
        prompt: str,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> Optional[str]:
        if not self.api_key:
            return None

        self._check_rate_limit()

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = requests.post(
                f"{self.base_url}/messages",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                data = response.json()
                if "content" in data and len(data["content"]) > 0:
                    return data["content"][0].get("text", "")
                return None

            raise ExternalAPIError(
                service="anthropic",
                endpoint="/messages",
                status_code=response.status_code,
                reason=response.text[:200],
            )

        except requests.Timeout:
            raise APITimeoutError(
                service="anthropic", endpoint="/messages", timeout_seconds=self.timeout
            )
        except ExternalAPIError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                service="anthropic", endpoint="/messages", status_code=0, reason=str(e)
            )
