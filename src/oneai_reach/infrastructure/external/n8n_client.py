"""n8n workflow automation client.

Triggers n8n workflows via webhook for event notifications and automation.
"""

import time
from datetime import datetime
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


class N8nClient:
    def __init__(self, settings: Settings) -> None:
        self.webhook_url = settings.n8n.webhook_url
        self.timeout = 5
        self.rate_limiter = RateLimiter(max_requests=30, window_seconds=60)

    def _check_rate_limit(self) -> None:
        if not self.rate_limiter.is_allowed():
            wait_time = self.rate_limiter.wait_time()
            raise APIRateLimitError(
                service="n8n",
                limit=self.rate_limiter.max_requests,
                window_seconds=self.rate_limiter.window_seconds,
                retry_after_seconds=int(wait_time) + 1,
            )

    @retry_with_backoff(max_retries=3, backoff_factor=1.0)
    def trigger_webhook(self, event_type: str, data: Dict[str, Any]) -> bool:
        if not self.webhook_url:
            return False

        self._check_rate_limit()

        payload = {
            "event": event_type,
            "timestamp": datetime.now().isoformat(),
            "source": "1ai-reach",
            "data": data,
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            return response.status_code < 300
        except requests.Timeout:
            raise APITimeoutError(
                service="n8n", endpoint=self.webhook_url, timeout_seconds=self.timeout
            )
        except Exception as e:
            raise ExternalAPIError(
                service="n8n", endpoint=self.webhook_url, status_code=0, reason=str(e)
            )

    def notify_conversation_started(
        self, phone: str, session: str, wa_number_id: str
    ) -> bool:
        return self.trigger_webhook(
            "cs_conversation_started",
            {
                "phone": phone,
                "session": session,
                "wa_number_id": wa_number_id,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def notify_escalation(self, phone: str, reason: str, conversation_id: int) -> bool:
        return self.trigger_webhook(
            "cs_escalated",
            {
                "phone": phone,
                "reason": reason,
                "conversation_id": conversation_id,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def notify_hot_lead(
        self, phone: str, message_count: int, conversation_id: int
    ) -> bool:
        return self.trigger_webhook(
            "cs_hot_lead",
            {
                "phone": phone,
                "message_count": message_count,
                "conversation_id": conversation_id,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def notify_purchase_signal(
        self, phone: str, message: str, conversation_id: int
    ) -> bool:
        return self.trigger_webhook(
            "cs_purchase_signal",
            {
                "phone": phone,
                "message": message,
                "conversation_id": conversation_id,
                "timestamp": datetime.now().isoformat(),
            },
        )
