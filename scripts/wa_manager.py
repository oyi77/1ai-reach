"""WAHA Multi-Session CRUD + QR Code Flow.

Manages WhatsApp sessions via the WAHA HTTP API and keeps the local
wa_numbers DB table in sync.  Provides a CLI for quick session ops.
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import requests

from config import (
    MCP_BASE_URL,
    WAHA_API_KEY,
    WAHA_DIRECT_API_KEY,
    WAHA_DIRECT_URL,
    WAHA_URL,
    WAHA_WEBHOOK_PATH,
    WAHA_WEBHOOK_SECRET,
)
from state_manager import (
    delete_wa_number,
    get_wa_number_by_session,
    get_wa_numbers,
    init_db,
    upsert_wa_number,
)


def _resolve_waha_url_key() -> tuple[str, str]:
    if WAHA_URL and WAHA_API_KEY:
        return str(WAHA_URL).rstrip("/"), str(WAHA_API_KEY)
    if WAHA_DIRECT_URL and WAHA_DIRECT_API_KEY:
        return str(WAHA_DIRECT_URL).rstrip("/"), str(WAHA_DIRECT_API_KEY)
    return "", ""


_BASE_URL, _API_KEY = _resolve_waha_url_key()
_HEADERS: dict[str, str] = {
    "X-Api-Key": _API_KEY,
    "Content-Type": "application/json",
}
_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get(path: str, **kwargs) -> requests.Response:
    h = {k: v for k, v in _HEADERS.items() if k != "Content-Type"}
    return requests.get(f"{_BASE_URL}{path}", headers=h, timeout=_TIMEOUT, **kwargs)


def _post(path: str, json_body: dict | None = None) -> requests.Response:
    return requests.post(
        f"{_BASE_URL}{path}", json=json_body, headers=_HEADERS, timeout=_TIMEOUT
    )


def _put(path: str, json_body: dict | None = None) -> requests.Response:
    return requests.put(
        f"{_BASE_URL}{path}", json=json_body, headers=_HEADERS, timeout=_TIMEOUT
    )


def _delete(path: str) -> requests.Response:
    h = {k: v for k, v in _HEADERS.items() if k != "Content-Type"}
    return requests.delete(f"{_BASE_URL}{path}", headers=h, timeout=_TIMEOUT)


# ---------------------------------------------------------------------------
# Public API — 8 functions
# ---------------------------------------------------------------------------


def list_sessions() -> list[dict]:
    """GET /api/sessions?all=true from WAHA, merge with wa_numbers DB.

    Returns list of dicts with: session_name, status, phone, label, mode.
    """
    db_map: dict[str, dict] = {}
    try:
        for rec in get_wa_numbers():
            db_map[rec["session_name"]] = rec
    except Exception as e:
        print(f"Warning: could not load wa_numbers: {e}", file=sys.stderr)

    waha_sessions: list[dict] = []
    try:
        r = _get("/api/sessions", params={"all": "true"})
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                waha_sessions = data
        else:
            print(
                f"Warning: WAHA list sessions {r.status_code}: {r.text[:200]}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"Warning: WAHA unreachable: {e}", file=sys.stderr)

    merged: list[dict] = []
    seen: set[str] = set()

    for s in waha_sessions:
        name = str(s.get("name") or "").strip()
        if not name:
            continue
        seen.add(name)
        db_rec = db_map.get(name, {})
        merged.append(
            {
                "session_name": name,
                "status": str(s.get("status") or "UNKNOWN"),
                "phone": db_rec.get("phone") or "",
                "label": db_rec.get("label") or "",
                "mode": db_rec.get("mode") or "cold",
            }
        )

    for name, rec in db_map.items():
        if name not in seen:
            merged.append(
                {
                    "session_name": name,
                    "status": "NOT_IN_WAHA",
                    "phone": rec.get("phone") or "",
                    "label": rec.get("label") or "",
                    "mode": rec.get("mode") or "cold",
                }
            )

    return merged


def create_session(
    session_name: str,
    phone: str = "",
    label: str = "",
    mode: str = "cs",
    persona: str = "",
) -> dict:
    """POST /api/sessions to WAHA + upsert wa_numbers in DB + configure webhooks."""
    result: dict = {"session_name": session_name, "ok": False}

    try:
        r = _post("/api/sessions", {"name": session_name})
        if r.status_code < 300:
            result["waha"] = r.json() if r.text.strip() else {}
            result["ok"] = True
            print(f"  WAHA session '{session_name}' created")
        else:
            result["error"] = f"WAHA {r.status_code}: {r.text[:200]}"
            print(
                f"  WAHA create error {r.status_code}: {r.text[:200]}",
                file=sys.stderr,
            )
    except Exception as e:
        result["error"] = str(e)
        print(f"  WAHA create failed: {e}", file=sys.stderr)

    try:
        kw: dict = {"phone": phone, "label": label, "mode": mode}
        if persona:
            kw["persona"] = persona
        upsert_wa_number(session_name, **kw)
        result["db"] = "ok"
    except Exception as e:
        result["db_error"] = str(e)
        print(f"  DB upsert failed: {e}", file=sys.stderr)

    if result["ok"]:
        webhook_url = f"{MCP_BASE_URL}{WAHA_WEBHOOK_PATH}"
        try:
            wh = configure_webhooks(session_name, webhook_url)
            result["webhooks"] = wh
        except Exception as e:
            result["webhook_error"] = str(e)
            print(f"  Webhook config failed: {e}", file=sys.stderr)

    return result


def delete_session(session_name: str) -> bool:
    """DELETE /api/sessions/:session from WAHA + delete from DB."""
    ok = False

    try:
        r = _delete(f"/api/sessions/{session_name}")
        if r.status_code < 300:
            print(f"  WAHA session '{session_name}' deleted")
            ok = True
        else:
            print(
                f"  WAHA delete error {r.status_code}: {r.text[:200]}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"  WAHA delete failed: {e}", file=sys.stderr)

    try:
        delete_wa_number(session_name)
        print(f"  DB record '{session_name}' deleted")
        ok = True
    except Exception as e:
        print(f"  DB delete failed: {e}", file=sys.stderr)

    return ok


def get_session_status(session_name: str) -> dict:
    """GET /api/sessions/:session from WAHA."""
    try:
        r = _get(f"/api/sessions/{session_name}")
        if r.status_code == 200:
            return r.json()
        return {"error": f"WAHA {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def get_qr_code(session_name: str) -> bytes | str:
    """GET /api/:session/auth/qr from WAHA.

    Returns QR image bytes on success, or an error string.
    """
    try:
        h = {k: v for k, v in _HEADERS.items() if k != "Content-Type"}
        r = requests.get(
            f"{_BASE_URL}/api/{session_name}/auth/qr",
            headers=h,
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            ct = r.headers.get("content-type", "")
            if "image" in ct:
                return r.content
            return r.text
        return f"QR error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return f"QR fetch failed: {e}"


def start_session(session_name: str) -> dict:
    """POST /api/sessions/:session/start."""
    try:
        r = _post(f"/api/sessions/{session_name}/start")
        if r.status_code < 300:
            print(f"  Session '{session_name}' started")
            return r.json() if r.text.strip() else {"ok": True}
        return {"error": f"WAHA {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def stop_session(session_name: str) -> dict:
    """POST /api/sessions/:session/stop."""
    try:
        r = _post(f"/api/sessions/{session_name}/stop")
        if r.status_code < 300:
            print(f"  Session '{session_name}' stopped")
            return r.json() if r.text.strip() else {"ok": True}
        return {"error": f"WAHA {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def configure_webhooks(session_name: str, webhook_url: str) -> dict:
    """PUT /api/sessions/:session with webhook config."""
    body = {
        "config": {
            "webhooks": [
                {
                    "url": webhook_url,
                    "events": ["message", "session.status"],
                    "hmac": {"key": WAHA_WEBHOOK_SECRET},
                }
            ]
        }
    }
    try:
        r = _put(f"/api/sessions/{session_name}", body)
        if r.status_code < 300:
            print(f"  Webhooks configured for '{session_name}' -> {webhook_url}")
            return r.json() if r.text.strip() else {"ok": True}
        return {"error": f"WAHA {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Module-level migration — register "default" session
# ---------------------------------------------------------------------------


def _register_default_session() -> None:
    """Register the existing 'default' WAHA session in wa_numbers if not already present."""
    try:
        init_db()
        if not get_wa_number_by_session("default"):
            upsert_wa_number(
                "default",
                phone="6282247006969",
                label="BerkahKarya Main",
                mode="cold",
            )
    except Exception as e:
        print(f"Warning: could not register default session: {e}", file=sys.stderr)


_register_default_session()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    p = argparse.ArgumentParser(description="WAHA session manager")
    p.add_argument("--list", action="store_true", help="List all sessions")
    p.add_argument("--create", metavar="NAME", help="Create a new session")
    p.add_argument("--phone", default="", help="Phone number for new session")
    p.add_argument("--label", default="", help="Label for new session")
    p.add_argument(
        "--mode",
        default="cs",
        choices=["cs", "warmcall", "cold"],
        help="Engine mode",
    )
    p.add_argument("--delete", metavar="NAME", help="Delete a session")
    p.add_argument("--status", metavar="NAME", help="Get session status")
    p.add_argument("--qr", metavar="NAME", help="Get QR code for session")
    args = p.parse_args()

    if args.list:
        print(json.dumps(list_sessions(), indent=2))
    elif args.create:
        result = create_session(
            args.create, phone=args.phone, label=args.label, mode=args.mode
        )
        print(json.dumps(result, indent=2))
    elif args.delete:
        ok = delete_session(args.delete)
        print("deleted" if ok else "failed")
    elif args.status:
        print(json.dumps(get_session_status(args.status), indent=2))
    elif args.qr:
        data = get_qr_code(args.qr)
        if isinstance(data, bytes):
            print(f"QR image: {len(data)} bytes (binary)")
        else:
            print(data)
    else:
        p.print_help()
