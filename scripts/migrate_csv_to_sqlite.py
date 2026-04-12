import sys

import pandas as pd

from config import LEADS_FILE, DB_FILE
import state_manager

_CSV_COLUMNS = [
    "id",
    "displayName",
    "formattedAddress",
    "internationalPhoneNumber",
    "phone",
    "websiteUri",
    "primaryType",
    "type",
    "source",
    "status",
    "contacted_at",
    "email",
    "linkedin",
    "followup_at",
    "replied_at",
    "research",
    "review_score",
    "review_issues",
]


def main():
    csv_path = str(LEADS_FILE)
    try:
        df = pd.read_csv(csv_path, dtype=str)
    except FileNotFoundError:
        print(f"WARNING: No CSV found at {csv_path} — nothing to migrate.")
        sys.exit(0)

    state_manager.init_db()

    migrated = 0
    for _, row in df.iterrows():
        lead = {}
        for col in _CSV_COLUMNS:
            val = row.get(col)
            if pd.isna(val) or str(val).strip().lower() in ("nan", "none", ""):
                lead[col] = None
            else:
                lead[col] = str(val)
        if not lead.get("id"):
            continue
        if not lead.get("status"):
            lead["status"] = "new"
        state_manager.upsert_lead(lead)
        migrated += 1

    print(f"Migrated {migrated} leads to {DB_FILE}")


if __name__ == "__main__":
    main()
