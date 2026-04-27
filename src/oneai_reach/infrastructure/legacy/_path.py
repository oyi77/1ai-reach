"""Shared path setup for legacy scripts/ imports."""

import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
_SCRIPTS_DIR = _ROOT_DIR / "scripts"


def _ensure_scripts_path() -> None:
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))


def _ensure_root_path() -> None:
    if str(_ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(_ROOT_DIR))