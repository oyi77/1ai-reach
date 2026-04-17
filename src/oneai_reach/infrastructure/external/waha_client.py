"""WAHA (WhatsApp HTTP API) client.

Manages WhatsApp sessions via the WAHA HTTP API for sending messages,
managing sessions, and configuring webhooks.
"""

import time
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


class WAHAClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = self._resolve_url(settings)
        self.api_key = self._resolve_api_key(settings)
        self.timeout = 15
        self.rate_limiter = RateLimiter(max_requests=20, window_seconds=60)

    def _resolve_url(self, settings: Settings) -> str:
        if settings.waha.url:
            return settings.waha.url.rstrip("/")
        if settings.waha.direct_url:
            return settings.waha.direct_url.rstrip("/")
        return ""

    def _resolve_api_key(self, settings: Settings) -> str:
        if settings.waha.api_key:
            return settings.waha.api_key
        if settings.waha.direct_api_key:
            return settings.waha.direct_api_key
        return ""

    def _headers(self, include_content_type: bool = True) -> Dict[str, str]:
        headers = {"X-Api-Key": self.api_key}
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _check_rate_limit(self) -> None:
        if not self.rate_limiter.is_allowed():
            wait_time = self.rate_limiter.wait_time()
            raise APIRateLimitError(
                service="waha",
                limit=self.rate_limiter.max_requests,
                window_seconds=self.rate_limiter.window_seconds,
                retry_after_seconds=int(wait_time) + 1,
            )

    @retry_with_backoff(max_retries=3, backoff_factor=1.0)
    def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        self._check_rate_limit()

        try:
            response = requests.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self._headers(include_content_type=False),
                timeout=self.timeout,
            )
            return response
        except requests.Timeout:
            raise APITimeoutError(
                service="waha", endpoint=path, timeout_seconds=self.timeout
            )
        except Exception as e:
            raise ExternalAPIError(
                service="waha", endpoint=path, status_code=0, reason=str(e)
            )

    @retry_with_backoff(max_retries=3, backoff_factor=1.0)
    def _post(
        self, path: str, json_body: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        self._check_rate_limit()

        try:
            response = requests.post(
                f"{self.base_url}{path}",
                json=json_body,
                headers=self._headers(),
                timeout=self.timeout,
            )
            return response
        except requests.Timeout:
            raise APITimeoutError(
                service="waha", endpoint=path, timeout_seconds=self.timeout
            )
        except Exception as e:
            raise ExternalAPIError(
                service="waha", endpoint=path, status_code=0, reason=str(e)
            )

    @retry_with_backoff(max_retries=3, backoff_factor=1.0)
    def _put(
        self, path: str, json_body: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        self._check_rate_limit()

        try:
            response = requests.put(
                f"{self.base_url}{path}",
                json=json_body,
                headers=self._headers(),
                timeout=self.timeout,
            )
            return response
        except requests.Timeout:
            raise APITimeoutError(
                service="waha", endpoint=path, timeout_seconds=self.timeout
            )
        except Exception as e:
            raise ExternalAPIError(
                service="waha", endpoint=path, status_code=0, reason=str(e)
            )

    @retry_with_backoff(max_retries=3, backoff_factor=1.0)
    def _delete(self, path: str) -> requests.Response:
        self._check_rate_limit()

        try:
            response = requests.delete(
                f"{self.base_url}{path}",
                headers=self._headers(include_content_type=False),
                timeout=self.timeout,
            )
            return response
        except requests.Timeout:
            raise APITimeoutError(
                service="waha", endpoint=path, timeout_seconds=self.timeout
            )
        except Exception as e:
            raise ExternalAPIError(
                service="waha", endpoint=path, status_code=0, reason=str(e)
            )

    def list_sessions(self) -> List[Dict[str, Any]]:
        try:
            response = self._get("/api/sessions", params={"all": "true"})
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
            return []
        except Exception:
            return []

    def create_session(self, session_name: str) -> Dict[str, Any]:
        try:
            response = self._post("/api/sessions", {"name": session_name})
            if response.status_code < 300:
                return response.json() if response.text.strip() else {"ok": True}
            raise ExternalAPIError(
                service="waha",
                endpoint="/api/sessions",
                status_code=response.status_code,
                reason=response.text[:200],
            )
        except ExternalAPIError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                service="waha", endpoint="/api/sessions", status_code=0, reason=str(e)
            )

    def delete_session(self, session_name: str) -> bool:
        try:
            response = self._delete(f"/api/sessions/{session_name}")
            return response.status_code < 300
        except Exception:
            return False

    def get_session_status(self, session_name: str) -> Dict[str, Any]:
        try:
            response = self._get(f"/api/sessions/{session_name}")
            if response.status_code == 200:
                return response.json()
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/sessions/{session_name}",
                status_code=response.status_code,
                reason=response.text[:200],
            )
        except ExternalAPIError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/sessions/{session_name}",
                status_code=0,
                reason=str(e),
            )

    def get_qr_code(self, session_name: str) -> bytes:
        try:
            response = self._get(f"/api/{session_name}/auth/qr")
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "image" in content_type:
                    return response.content
                raise ExternalAPIError(
                    service="waha",
                    endpoint=f"/api/{session_name}/auth/qr",
                    status_code=response.status_code,
                    reason="Response is not an image",
                )
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/{session_name}/auth/qr",
                status_code=response.status_code,
                reason=response.text[:200],
            )
        except ExternalAPIError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/{session_name}/auth/qr",
                status_code=0,
                reason=str(e),
            )

    def start_session(self, session_name: str) -> Dict[str, Any]:
        try:
            response = self._post(f"/api/sessions/{session_name}/start")
            if response.status_code < 300:
                return response.json() if response.text.strip() else {"ok": True}
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/sessions/{session_name}/start",
                status_code=response.status_code,
                reason=response.text[:200],
            )
        except ExternalAPIError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/sessions/{session_name}/start",
                status_code=0,
                reason=str(e),
            )

    def stop_session(self, session_name: str) -> Dict[str, Any]:
        try:
            response = self._post(f"/api/sessions/{session_name}/stop")
            if response.status_code < 300:
                return response.json() if response.text.strip() else {"ok": True}
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/sessions/{session_name}/stop",
                status_code=response.status_code,
                reason=response.text[:200],
            )
        except ExternalAPIError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/sessions/{session_name}/stop",
                status_code=0,
                reason=str(e),
            )

    def configure_webhooks(
        self, session_name: str, webhook_url: str, webhook_secret: str
    ) -> Dict[str, Any]:
        body = {
            "config": {
                "webhooks": [
                    {
                        "url": webhook_url,
                        "events": ["message", "session.status"],
                        "hmac": {"key": webhook_secret},
                    }
                ]
            }
        }
        try:
            response = self._put(f"/api/sessions/{session_name}", body)
            if response.status_code < 300:
                return response.json() if response.text.strip() else {"ok": True}
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/sessions/{session_name}",
                status_code=response.status_code,
                reason=response.text[:200],
            )
        except ExternalAPIError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                service="waha",
                endpoint=f"/api/sessions/{session_name}",
                status_code=0,
                reason=str(e),
            )
