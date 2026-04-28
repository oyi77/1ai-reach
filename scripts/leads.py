import os

import pandas as pd

from config import LEADS_FILE as _LEADS_PATH
import state_manager

LEADS_FILE = str(_LEADS_PATH)

_STR_COLS = (
    "email",
    "phone",
    "internationalPhoneNumber",
    "linkedin",
    "status",
    "contacted_at",
    "followup_at",
    "replied_at",
    "research",
    "review_score",
    "review_issues",
    "source",
    "displayName",
    "websiteUri",
    "formattedAddress",
    "primaryType",
    "type",
    "matched_services",
    "tier",
    "service_proposed",
)

FUNNEL_STAGES = (
    "new",
    "enriched",
    "draft_ready",
    "needs_revision",
    "reviewed",
    "contacted",
    "followed_up",
    "replied",
    "meeting_booked",
    "won",
    "lost",
    "cold",
    "unsubscribed",
)

_DEFAULTS = {
    "status": "new",
    "contacted_at": None,
    "followup_at": None,
    "replied_at": None,
    "research": None,
    "review_score": None,
    "review_issues": None,
}

state_manager.init_db()


def load_leads(path: str = LEADS_FILE) -> pd.DataFrame | None:
    rows = state_manager.get_all_leads()
    if not rows:
        if not os.path.exists(path):
            print(f"No leads file found at {path}.")
            return None
        df = pd.read_csv(path, dtype={c: str for c in _STR_COLS})
    else:
        df = pd.DataFrame(rows)
    for col, default in _DEFAULTS.items():
        if col not in df.columns:
            df[col] = default
    for col in _STR_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).replace({"None": None, "nan": None, "<NA>": None})
    return df


def save_leads(df: pd.DataFrame, path: str = LEADS_FILE) -> None:
    for _, row in df.iterrows():
        lead = row.to_dict()
        for k, v in lead.items():
            if pd.isna(v):
                lead[k] = None
            else:
                lead[k] = str(v)
        if not lead.get("id"):
            continue
        state_manager.upsert_lead(lead)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Saved {len(df)} leads to {path}")


def funnel_summary(path: str = LEADS_FILE) -> None:
    counts = state_manager.count_by_status()
    if not counts:
        df = load_leads(path)
        if df is None:
            return
        counts = df["status"].value_counts().to_dict()

    print("\n📊 Funnel Summary")
    print(f"{'Stage':<20} {'Count':>6}")
    print("-" * 28)
    total = 0
    for stage in FUNNEL_STAGES:
        n = counts.get(stage, 0)
        total += n
        if n > 0:
            bar = "█" * min(n, 30)
            print(f"{stage:<20} {n:>6}  {bar}")
    print(f"\n  Total leads: {total}")
