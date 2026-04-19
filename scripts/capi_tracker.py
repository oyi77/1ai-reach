#!/usr/bin/env python3
"""
DEPRECATED: This script is deprecated. Use `oneai-reach track-capi` instead.

Backward compatibility shim for capi_tracker.py
"""
import sys
import warnings
from pathlib import Path

# Show deprecation warning
warnings.warn(
    "scripts/capi_tracker.py is deprecated. Use 'oneai-reach track-capi' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Add src to path for imports
_root = Path(__file__).resolve().parent.parent
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Import and call new CLI
from oneai_reach.cli.main import cli

# Backward compatibility functions
def track_lead(phone: str) -> None:
    """Track a new lead conversion (stub for backward compatibility)."""
    pass


def track_purchase(phone: str) -> None:
    """Track a purchase conversion (stub for backward compatibility)."""
    pass


def track_atc(phone: str) -> None:
    """Track Add to Cart event (stub for backward compatibility)."""
    pass


if __name__ == "__main__":
    sys.exit(cli())
