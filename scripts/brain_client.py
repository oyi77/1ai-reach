"""
BerkahKarya Hub Brain client.

Connects to the hub's /brain/* API (FastAPI, port 9099) to:
  - Store outreach learnings (what proposals got replies, what verticals convert)
  - Query past strategy before generating proposals
  - Sync pipeline outcomes for all hub agents to learn from
  - Recall, list, and browse brain entries

Falls back silently if the hub is offline — never blocks the pipeline.

Hub API conventions:
  - Search uses `q` param (not `query`)
  - Add uses `wing/room/hall` (PARA-style organization, not category/agent_id)
  - Timeline returns {results: [...]} with service filter
"""
import sys
from typing import Optional

try:
    import requests as _requests
    _HTTP_OK = True
except ImportError:
    _HTTP_OK = False

from config import HUB_URL, HUB_API_KEY

_BASE = HUB_URL.rstrip("/")
_TIMEOUT = 15
_TIMEOUT_FAST = 3

WING_1AI = "1ai-reach"
ROOM_OUTREACH = "outreach"
ROOM_PIPELINE = "pipeline"
ROOM_STRATEGY = "strategy"


def _extract_content(raw) -> str:
    """Extract clean text from brain search result content field.

    The hub may return MemPalace results as stringified dicts with a 'text' key,
    or GBrain results with empty content but a title, or plain FTS5 text.
    """
    if not raw:
        return ""
    if isinstance(raw, dict):
        text = raw.get("text", raw.get("compiled_truth", raw.get("snippet", "")))
        if isinstance(text, str) and text.strip():
            return text.strip()
        return str(raw)[:500]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return ""
        # MemPalace returns entire response dict stringified in content field.
        # Extract text values using regex since it may be truncated (invalid JSON/Python).
        import re as _re
        _MP_PATTERN = _re.compile(r"'text':\s*'([^']*(?:\\'[^']*)*?)'")
        texts = _MP_PATTERN.findall(s)
        if texts:
            return "; ".join(t.strip() for t in texts if t.strip())[:500]
        # Fallback: try JSON parse for well-formed content
        if s.startswith("{") and '"text"' in s:
            try:
                import json as _json
                parsed = _json.loads(s)
                if isinstance(parsed, dict):
                    text = parsed.get("text", "")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
                    results = parsed.get("results", [])
                    if isinstance(results, list) and results:
                        parts = [item.get("text", "")[:200] for item in results[:5] if item.get("text")]
                        if parts:
                            return "; ".join(parts)
            except Exception:
                pass
        return s
    return str(raw)[:500]


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if HUB_API_KEY:
        h["X-Api-Key"] = HUB_API_KEY
    return h


def _get(path: str, params: dict = None) -> Optional[dict]:
    if not _HTTP_OK:
        return None
    try:
        r = _requests.get(f"{_BASE}{path}", params=params, headers=_headers(), timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[brain] GET {path} failed: {e}", file=sys.stderr)
        return None


def _post(path: str, data: dict, retries: int = 1) -> Optional[dict]:
    if not _HTTP_OK:
        return None
    for attempt in range(retries + 1):
        try:
            r = _requests.post(f"{_BASE}{path}", json=data, headers=_headers(), timeout=_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < retries:
                import time as _time
                _time.sleep(0.5 * (attempt + 1))
                continue
            print(f"[brain] POST {path} failed: {e}", file=sys.stderr)
            return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search(query: str, limit: int = 5, wing: str = None, room: str = None,
           service: str = None, source: str = None) -> list[dict]:
    """Search brain across all backends (GBrain, MemPalace, FTS5, files).

    Returns list of {content, score, source, title, slug, service, page_type}.
    """
    params = {"q": query, "limit": str(limit)}
    if wing:
        params["wing"] = wing
    if room:
        params["room"] = room
    if service:
        params["service"] = service
    if source:
        params["source"] = source

    result = _get("/brain/search", params)
    if result and isinstance(result, dict):
        return result.get("results", [])
    if result and isinstance(result, list):
        return result
    return []


def add(content: str, wing: str = WING_1AI, room: str = ROOM_OUTREACH,
        hall: str = None) -> Optional[str]:
    """Add a memory drawer to the brain. Returns drawer_id or None.

    Uses PARA-style organization:
      wing: service/agent (e.g. "1ai-reach", "opencode", "paperclip")
      room: topic area (e.g. "outreach", "strategy", "pipeline")
      hall: sub-category (optional)
    """
    payload = {"content": content, "wing": wing, "room": room}
    if hall:
        payload["hall"] = hall

    result = _post("/brain/add", payload)
    if result:
        return result.get("drawer_id") or result.get("id") or result.get("memory_id")
    return None


def recall(query: str, limit: int = 3) -> list[dict]:
    """Quick recall — alias for search with default params."""
    return search(query, limit=limit)


def get_strategy(vertical: str, location: str = "Jakarta", service: str = None) -> str:
    """Query brain for outreach strategies that worked in this vertical.

    Returns a formatted string to inject into proposal prompts, or "" if nothing found.
    """
    parts = [f"successful outreach proposal {vertical} {location}"]
    if service:
        parts.append(service)
    parts.append("reply conversion")
    query = " ".join(parts)

    results = search(query, limit=5, wing=WING_1AI)
    if not results:
        results = search(query, limit=5)

    if not results:
        return ""

    lines = []
    seen = set()
    for r in results:
        content = _extract_content(r.get("content", ""))
        if not content and r.get("title"):
            content = r.get("title", "").strip()
        if not content:
            continue
        sig = content[:80].lower()
        if sig in seen:
            continue
        seen.add(sig)
        lines.append(f"- {content[:300]}")

    if not lines:
        return ""
    return "Past outreach intelligence from our brain:\n" + "\n".join(lines)


def learn_outcome(
    lead_name: str,
    vertical: str,
    status: str,
    pain_points: str = "",
    review_score: str = "",
    decision_maker: str = "",
    service_type: str = "",
) -> Optional[str]:
    """Store an outreach outcome in the brain so future generations can learn.

    Called after key funnel transitions (contacted, replied, won, lost, cold).
    Returns the drawer_id or None.
    """
    if status not in ("replied", "won", "lost", "cold", "contacted"):
        return None

    outcome_map = {
        "replied": "got a reply",
        "won": "converted to a deal",
        "lost": "did not convert (lost)",
        "cold": "went cold (no response after follow-up)",
        "contacted": "was contacted",
    }
    outcome = outcome_map.get(status, status)

    parts = [f"Outreach to {lead_name} ({vertical}) {outcome}."]
    if decision_maker:
        parts.append(f"Decision maker: {decision_maker}.")
    if pain_points:
        parts.append(f"Pain points addressed: {pain_points}.")
    if review_score:
        parts.append(f"Proposal score: {review_score}/10.")
    if service_type:
        parts.append(f"Service proposed: {service_type}.")

    content = " ".join(parts)
    room = "outreach_win" if status in ("replied", "won") else "outreach_loss"
    drawer_id = add(content, wing=WING_1AI, room=room)
    if drawer_id:
        print(f"[brain] Stored outcome: {content[:80]}...")
    return drawer_id


def learn_batch_outcomes(df) -> None:
    """Store all new outcomes from a leads DataFrame that haven't been stored yet."""
    from utils import parse_display_name

    target_statuses = {"replied", "won", "lost", "cold"}
    stored = 0
    for _, row in df.iterrows():
        status = str(row.get("status") or "").strip()
        if status not in target_statuses:
            continue

        name = parse_display_name(row.get("displayName"))
        vertical = str(row.get("type") or row.get("primaryType") or "Business")
        research = str(row.get("research") or "")
        score = str(row.get("review_score") or "")

        dm = ""
        if "Decision maker:" in research:
            dm = research.split("Decision maker:")[-1].split(".")[0].strip()

        learn_outcome(
            lead_name=name,
            vertical=vertical,
            status=status,
            pain_points=research[:200] if research else "",
            review_score=score,
            decision_maker=dm,
        )
        stored += 1

    if stored:
        print(f"[brain] Synced {stored} outcomes to hub brain.")


def stats() -> Optional[dict]:
    """Get brain stats (gbrain pages, mempalace drawers, by service)."""
    return _get("/brain/stats")


def timeline(service: str = None, limit: int = 20) -> list[dict]:
    """Get recent brain entries, optionally filtered by service."""
    params = {"limit": str(limit)}
    if service:
        params["service"] = service

    result = _get("/brain/timeline", params)
    if result and isinstance(result, dict):
        return result.get("results", [])
    if result and isinstance(result, list):
        return result
    return []


def list_entries(wing: str = None, limit: int = 100) -> list[dict]:
    """List brain entries, optionally filtered by wing (agent)."""
    params = {"limit": str(limit)}
    if wing:
        params["wing"] = wing

    result = _get("/brain/list", params)
    if result and isinstance(result, dict):
        return result.get("memories", result.get("results", []))
    if result and isinstance(result, list):
        return result
    return []


def gbrain_search(query: str, limit: int = 5) -> list[dict]:
    """Search GBrain directly for rich knowledge base content."""
    params = {"q": query, "limit": str(limit)}
    result = _get("/brain/gbrain/search", params)
    if result and isinstance(result, dict):
        return result.get("results", [])
    if result and isinstance(result, list):
        return result
    return []


def gbrain_get_page(slug: str) -> Optional[dict]:
    """Get a specific GBrain page by slug."""
    return _get(f"/brain/gbrain/page/{slug}")


def is_online() -> bool:
    """Quick health check — returns True if hub brain is reachable."""
    if not _HTTP_OK:
        return False
    try:
        r = _requests.get(f"{_BASE}/health", headers=_headers(), timeout=_TIMEOUT_FAST)
        return r.status_code < 300
    except Exception:
        return False
