import json
import re

from config import PROPOSALS_DIR


def is_empty(value) -> bool:
    """Return True if a value is effectively missing (None, NaN, empty string, 'nan', 'none')."""
    if value is None:
        return True
    s = str(value).strip().lower()
    return s in ("", "nan", "none")


def normalize_phone(raw: str) -> str | None:
    """Normalize an Indonesian phone number to +62xxx format. Returns None if invalid."""
    if is_empty(raw):
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if digits.startswith("08"):
        digits = "62" + digits[1:]
    elif digits.startswith("0"):
        digits = "62" + digits[1:]
    elif not digits.startswith("62"):
        digits = "62" + digits
    return "+" + digits


def parse_display_name(raw) -> str:
    """Extract a business name from a raw displayName value (plain string or stringified dict)."""
    if isinstance(raw, str) and raw.startswith("{"):
        try:
            return json.loads(raw.replace("'", '"')).get("text", "Business")
        except Exception:
            return "Business"
    if not is_empty(raw):
        return str(raw)
    return "Business"


def safe_filename(name: str) -> str:
    """Convert a name to a filesystem-safe string."""
    return "".join(c if c.isalnum() else "_" for c in str(name))


def draft_path(lead_id, name: str) -> str:
    return str(PROPOSALS_DIR / f"{lead_id}_{safe_filename(name)}.txt")
