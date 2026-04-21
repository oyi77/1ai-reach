#!/usr/bin/env python3
"""
DEPRECATED: This script is deprecated. Use `oneai-reach enrich` instead.

Backward compatibility shim for enricher.py
"""
import sys
import warnings
from pathlib import Path

# Show deprecation warning
warnings.warn(
    "scripts/enricher.py is deprecated. Use 'oneai-reach enrich' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Add src to path for imports
_root = Path(__file__).resolve().parent.parent
_src = _root / "src"

# Import and call new CLI
from oneai_reach.cli.main import cli

if __name__ == "__main__":
    sys.exit(cli())
