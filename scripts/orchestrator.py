#!/usr/bin/env python3
"""
DEPRECATED: This script is deprecated. Use `oneai-reach orchestrate` instead.

Backward compatibility shim for orchestrator.py
"""
import sys
import warnings
from pathlib import Path

# Show deprecation warning
warnings.warn(
    "scripts/orchestrator.py is deprecated. Use 'oneai-reach orchestrate' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Package is installed in editable mode, imports work without sys.path manipulation

# Import and call new CLI
from oneai_reach.cli.main import cli

if __name__ == "__main__":
    sys.exit(cli())
