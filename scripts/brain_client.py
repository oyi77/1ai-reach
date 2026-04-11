"""
BerkahKarya Hub Brain client.

Connects to the hub's /brain/* API (FastAPI, port 9099) to:
  - Store outreach learnings (what proposals got replies, what verticals convert)
  - Query past strategy before generating proposals
  - Sync pipeline outcomes for all hub agents to learn from

Falls back silently if the hub is offline — never blocks the pipeline.
"""
import sys
from datetime import datetime, timezone
from typing import Optional

try:
    import requests as _requests
    _HTTP_OK = True
except ImportError:
    _HTTP_OK = False

from config import HUB_URL, HUB_API_KEY

_BASE    = HUB_URL.rstrip("/")
_TIMEOUT       = 15   # seconds — for search/add calls
_TIMEOUT_FAST  = 3    # seconds — for health checks only


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


def _post(path: str, data: dict) -> Optional[dict]:
    if not _HTTP_OK:
        return None
    try:
        r = _requests.post(f"{_BASE}{path}", json=data, headers=_headers(), timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[brain] POST {path} failed: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search(query: str, limit: int = 3, method: str = "hybrid") -> list[dict]:
    """Search brain for relevant memories. Returns list of {content, score, category}."""
    result = _get("/brain/search", {"query": query, "limit": limit, "method": method})
    if result and isinstance(result, list):
        return result
    if result and isinstance(result, dict):
        return result.get("results", [])
    return []


def add(content: str, category: str = "outreach", agent_id: str = "1ai-engage") -> Optional[str]:
    """Add a memory to the shared brain. Returns memory ID or None."""
    result = _post("/brain/add", {
        "content": content,
        "category": category,
        "agent_id": agent_id,
        "metadata": {"source": "1ai-engage", "ts": datetime.now(timezone.utc).isoformat()}
    })
    if result:
        return result.get("id") or result.get("memory_id")
    return None


def get_strategy(vertical: str, location: str = "Jakarta") -> str:
    """
    Query brain for outreach strategies that worked in this vertical.
    Returns a formatted string to inject into proposal prompts, or "" if nothing found.
    """
    query = f"successful outreach proposal {vertical} {location} reply conversion"
    results = search(query, limit=3)
    if not results:
        return ""

    lines = []
    for r in results:
        content = r.get("content", "").strip()
        if content:
            lines.append(f"- {content[:200]}")
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
) -> None:
    """
    Store an outreach outcome in the brain so future generations can learn.
    Called after key funnel transitions (contacted, replied, won, lost, cold).
    """
    # Only store meaningful outcomes
    if status not in ("replied", "won", "lost", "cold", "contacted"):
        return

    outcome_map = {
        "replied":   "got a reply",
        "won":       "converted to a deal",
        "lost":      "did not convert (lost)",
        "cold":      "went cold (no response after follow-up)",
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

    content = " ".join(parts)
    category = "outreach_win" if status in ("replied", "won") else "outreach_loss"
    add(content, category=category)
    print(f"[brain] Stored outcome: {content[:80]}...")


def learn_batch_outcomes(df) -> None:
    """
    Called at end of pipeline to store all new outcomes (replied/won/cold/lost)
    that haven't been stored yet. Checks brain for existing entries to avoid duplication.
    """
    from utils import parse_display_name

    target_statuses = {"replied", "won", "lost", "cold"}
    stored = 0
    for _, row in df.iterrows():
        status = str(row.get("status") or "").strip()
        if status not in target_statuses:
            continue

        name     = parse_display_name(row.get("displayName"))
        vertical = str(row.get("type") or row.get("primaryType") or "Business")
        research = str(row.get("research") or "")
        score    = str(row.get("review_score") or "")

        # Extract decision maker from research field if available
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
    """Get brain stats (total memories, by category)."""
    return _get("/brain/stats")


def is_online() -> bool:
    """Quick health check — returns True if hub brain is reachable."""
    if not _HTTP_OK:
        return False
    try:
        r = _requests.get(f"{_BASE}/health", headers=_headers(), timeout=_TIMEOUT_FAST)
        return r.status_code < 300
    except Exception:
        return False
