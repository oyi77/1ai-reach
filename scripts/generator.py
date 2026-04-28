"""
AI proposal generator — dynamic, brain-informed proposals.

For each eligible lead:
  1. Queries Hub Brain for BerkahKarya capability matrix
  2. Loads prospect research brief (from data/research/ if available)
  3. Builds a dynamic prompt — no static boilerplate
  4. Passes research + lead info + capabilities to Claude for a personalized proposal
  5. Falls back to gemini → oracle if Claude unavailable
  6. Skips lead (logs error) if all LLMs fail — no template fallback

CLI flags:
  --lead-id <id>   Process only one specific lead (by DB id)
  --dry-run        Print prompt instead of calling LLM
"""

import argparse
import os
import pandas as pd
import sys

from leads import load_leads
from utils import parse_display_name, draft_path, is_empty
from config import PROPOSALS_DIR as _PROPOSALS_DIR
import state_manager as _sm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from oneai_reach.config.settings import get_settings
from oneai_reach.application.outreach.generator_service import GeneratorService

PROPOSALS_DIR = str(_PROPOSALS_DIR)


def _process_single_lead(
    service: GeneratorService, lead: dict, dry_run: bool = False
) -> bool:
    """Process one lead. Returns True if proposal was generated/saved."""
    lead_id = lead["id"]
    lead_name = parse_display_name(lead.get("displayName"))
    business_type = str(lead.get("type") or lead.get("primaryType") or "Business")

    print(f"Generating proposal for {lead_name} ({business_type})...")

    try:
        proposal_text = service.generate_proposal(lead, dry_run=dry_run)
    except Exception as e:
        print(
            f"ERROR: Failed to generate proposal for {lead_name}: {e}", file=sys.stderr
        )
        return False

    if dry_run:
        return True

    if not proposal_text:
        return False

    path = draft_path(lead_id, lead_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(proposal_text)

    _sm.update_lead_status(lead_id, "draft_ready")
    _sm.add_event_log(lead_id, "proposal_generated", f"Draft saved to {path}")
    return True


def process_proposals(lead_id: str = None, dry_run: bool = False) -> None:
    """
    Main entry point.
    - If lead_id is given: process only that lead.
    - Otherwise: process all eligible leads (enriched or needs_revision).
    """
    os.makedirs(PROPOSALS_DIR, exist_ok=True)

    config = get_settings()
    service = GeneratorService(config)

    if lead_id:
        lead = _sm.get_lead_by_id(lead_id)
        if not lead:
            print(f"ERROR: Lead {lead_id} not found in database.", file=sys.stderr)
            sys.exit(1)
        _process_single_lead(service, lead, dry_run=dry_run)
        return

    df = load_leads()
    if df is None:
        leads = _sm.get_leads_by_status(["enriched", "needs_revision"])
        if not leads:
            print("No eligible leads found.")
            return
        generated = skipped = 0
        for lead in leads:
            email = str(lead.get("email") or "").strip()
            if is_empty(email):
                skipped += 1
                continue
            ok = _process_single_lead(service, lead, dry_run=dry_run)
            if ok:
                generated += 1
            else:
                skipped += 1
        print(f"\nGeneration complete. {generated} generated, {skipped} skipped.")
        return

    generated = skipped = 0
    for index, row in df.iterrows():
        name = parse_display_name(row.get("displayName"))
        status = str(row.get("status") or "")

        if status in (
            "reviewed",
            "contacted",
            "followed_up",
            "replied",
            "meeting_booked",
            "won",
            "lost",
        ):
            skipped += 1
            continue

        val = row.get("email"); email = "" if pd.isna(val) else str(val).strip()
        if is_empty(email):
            skipped += 1
            continue

        path = draft_path(index, name)
        if os.path.exists(path) and status != "needs_revision":
            skipped += 1
            continue

        business = str(row.get("type") or row.get("primaryType") or "Business")
        csv_research = str(row.get("research") or "")

        lead_dict = {
            "id": str(index),
            "displayName": row.get("displayName"),
            "type": row.get("type"),
            "primaryType": row.get("primaryType"),
            "websiteUri": row.get("websiteUri") or row.get("website"),
            "email": row.get("email"),
            "phone": row.get("phone") or row.get("internationalPhoneNumber"),
            "formattedAddress": row.get("formattedAddress") or row.get("address"),
            "research": csv_research,
        }

        print(f"Generating proposal for {name} ({business})...")

        try:
            proposal_text = service.generate_proposal(lead_dict, dry_run=dry_run)
        except Exception as e:
            print(
                f"ERROR: Failed to generate proposal for {name}: {e}", file=sys.stderr
            )
            continue

        if dry_run:
            generated += 1
            continue

        if not proposal_text:
            continue

        with open(path, "w") as f:
            f.write(proposal_text)
        generated += 1

    print(f"\nGeneration complete. {generated} generated, {skipped} skipped.")


def main():
    parser = argparse.ArgumentParser(description="Generate AI proposals for leads")
    parser.add_argument(
        "--lead-id",
        type=str,
        default=None,
        help="Process only this specific lead (by DB id)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompt instead of calling LLM",
    )
    args = parser.parse_args()
    process_proposals(lead_id=args.lead_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
