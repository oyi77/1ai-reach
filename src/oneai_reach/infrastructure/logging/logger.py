"""Structured logging infrastructure with JSON formatter and correlation ID support."""

import logging
import json
import sys
from pathlib import Path
from contextvars import ContextVar
from functools import lru_cache
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

# Correlation ID context variable for request tracing
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default=None)

# Logs directory
LOGS_DIR = Path(__file__).parent.parent.parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output (development)."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        color = self.COLORS.get(record.levelname, self.RESET)
        correlation_id = correlation_id_var.get()
        correlation_str = f" [{correlation_id}]" if correlation_id else ""

        return (
            f"{color}{record.levelname:8}{self.RESET} "
            f"{record.name:30} {record.getMessage()}{correlation_str}"
        )


@lru_cache(maxsize=128)
def get_logger(name: str) -> logging.Logger:
    """Get or create a configured logger.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Skip if already configured
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler (colored, human-readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    # File handler (JSON, rotated)
    log_file = LOGS_DIR / f"{name.replace('.', '_')}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


@contextmanager
def correlation_id_context(correlation_id: str):
    """Context manager for correlation ID injection.

    Usage:
        with correlation_id_context('req-123'):
            logger.info('Processing request')  # Will include correlation_id in logs
    """
    token = correlation_id_var.set(correlation_id)
    try:
        yield
    finally:
        correlation_id_var.reset(token)


def get_correlation_id() -> str | None:
    """Get current correlation ID."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID directly."""
    correlation_id_var.set(correlation_id)
