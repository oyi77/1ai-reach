import os
from pathlib import Path

import pandas as pd

from config import LEADS_FILE as _LEADS_PATH
from utils import is_empty

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
)

# Full funnel stages (in order):
#   new → enriched → draft_ready → needs_revision → reviewed →
#   contacted → followed_up → replied → meeting_booked → won / lost / cold / unsubscribed
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


def load_leads(path: str = LEADS_FILE) -> pd.DataFrame | None:
    if not os.path.exists(path):
        print(f"No leads file found at {path}.")
        return None
    df = pd.read_csv(path, dtype={c: str for c in _STR_COLS})
    # Ensure all funnel-tracking columns always exist
    defaults = {
        "status": "new",
        "contacted_at": None,
        "followup_at": None,
        "replied_at": None,
        "research": None,
        "review_score": None,
        "review_issues": None,
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
    return df


def save_leads(df: pd.DataFrame, path: str = LEADS_FILE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Saved {len(df)} leads to {path}")


def funnel_summary(path: str = LEADS_FILE) -> None:
    """Print a quick funnel stage breakdown."""
    df = load_leads(path)
    if df is None:
        return
    counts = df["status"].value_counts()
    print("\n📊 Funnel Summary")
    print(f"{'Stage':<20} {'Count':>6}")
    print("-" * 28)
    for stage in FUNNEL_STAGES:
        n = counts.get(stage, 0)
        if n > 0:
            bar = "█" * min(n, 30)
            print(f"{stage:<20} {n:>6}  {bar}")
    total = len(df)
    print(f"\n  Total leads: {total}")
    has_email = (~df["email"].apply(is_empty)).sum()
    has_phone = (~df["internationalPhoneNumber"].apply(is_empty)).sum()
    print(f"  With email:  {has_email}")
    print(f"  With phone:  {has_phone}")
