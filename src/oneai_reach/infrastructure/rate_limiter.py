"""Rate limiting and retry utilities for external API calls.

Provides:
- Exponential backoff retry decorator
- Rate limit tracking per service
- Circuit breaker pattern for failing services
"""

import asyncio
import time
from collections import defaultdict
from functools import wraps
from typing import Any, Callable, Optional

from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open (service failing)."""
    pass


class RateLimiter:
    """Token bucket rate limiter for API calls.
    
    Usage:
        limiter = RateLimiter(calls_per_minute=60)
        await limiter.acquire()  # Blocks until token available
    """
    
    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.tokens = calls_per_minute
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens, blocking if necessary.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True when tokens acquired
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.calls_per_minute,
                    self.tokens + elapsed * (self.calls_per_minute / 60.0)
                )
                self.last_update = now
                
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                
                # Calculate wait time
                wait_time = (tokens - self.tokens) * (60.0 / self.calls_per_minute)
                await asyncio.sleep(wait_time)


class CircuitBreaker:
    """Circuit breaker for failing external services.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service failing, requests fail immediately
    - HALF_OPEN: Testing if service recovered
    
    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
        async with breaker.call():
            await make_api_call()
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exceptions: tuple = (Exception,),
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        async with self._lock:
            if self.state == "OPEN":
                if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info("Circuit breaker entering HALF_OPEN state")
                else:
                    raise CircuitBreakerOpen("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                    logger.info("Circuit breaker CLOSED - service recovered")
            return result
        except self.expected_exceptions as e:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.monotonic()
                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.warning(f"Circuit breaker OPEN - {self.failure_count} failures")
            raise


class RetryWithBackoff:
    """Retry decorator with exponential backoff.
    
    Usage:
        @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
        async def api_call():
            ...
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        exceptions: tuple = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.exceptions = exceptions
    
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(self.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except self.exceptions as e:
                    last_exception = e
                    
                    if attempt == self.max_retries:
                        break
                    
                    delay = min(
                        self.base_delay * (self.exponential_base ** attempt),
                        self.max_delay
                    )
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
            
            raise last_exception
        
        return wrapper


# Global rate limiters per service
_rate_limiters: dict[str, RateLimiter] = defaultdict(lambda: RateLimiter(calls_per_minute=60))
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_rate_limiter(service: str, calls_per_minute: int = 60) -> RateLimiter:
    """Get or create rate limiter for a service.
    
    Args:
        service: Service name (e.g., "google_places", "brevo", "jina")
        calls_per_minute: Rate limit
        
    Returns:
        RateLimiter instance
    """
    if service not in _rate_limiters:
        _rate_limiters[service] = RateLimiter(calls_per_minute)
    return _rate_limiters[service]


def get_circuit_breaker(
    service: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
) -> CircuitBreaker:
    """Get or create circuit breaker for a service.
    
    Args:
        service: Service name
        failure_threshold: Failures before opening circuit
        recovery_timeout: Seconds before attempting recovery
        
    Returns:
        CircuitBreaker instance
    """
    if service not in _circuit_breakers:
        _circuit_breakers[service] = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _circuit_breakers[service]


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator for retry with exponential backoff.
    
    Args:
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Exceptions to catch and retry
        
    Returns:
        Decorated function
    """
    return RetryWithBackoff(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        exceptions=exceptions,
    )
