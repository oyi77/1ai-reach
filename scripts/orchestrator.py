"""
Full outreach pipeline orchestrator.

Thin wrapper around OrchestratorService from application layer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.outreach import OrchestratorService
from oneai_reach.config.settings import get_settings


def main() -> None:
    args = sys.argv[1:]
    mode = "full"
    query = None

    if "--dry-run" in args:
        mode = "dry_run"
        args.remove("--dry-run")
    elif "--followup-only" in args:
        mode = "followup"
        args.remove("--followup-only")
    elif "--enrich-only" in args:
        mode = "enrich"
        args.remove("--enrich-only")
    elif "--sync-only" in args:
        mode = "sync"
        args.remove("--sync-only")

    if args:
        query = " ".join(args)

    settings = get_settings()
    service = OrchestratorService(settings)

    if mode == "sync":
        service.run_sync_only()
        print("\n✅ Sync complete.")
        return

    if mode == "followup":
        service.run_followup_only()
        print("\n✅ Follow-up cycle complete.")
        return

    if mode == "enrich":
        service.run_enrich_only()
        print("\n✅ Enrichment complete.")
        return

    if not query:
        print("Usage: python3 1ai-reach/scripts/orchestrator.py <query> [--dry-run]")
        print("  e.g. python3 1ai-reach/scripts/orchestrator.py 'Digital Agency in Jakarta'")
        print("  e.g. python3 1ai-reach/scripts/orchestrator.py --followup-only")
        print("  e.g. python3 1ai-reach/scripts/orchestrator.py --sync-only")
        return

    dry = mode == "dry_run"
    service.run_full_pipeline(query, dry_run=dry)

    print(f"\n{'=' * 60}")
    print("✅ Pipeline complete.")
    print(f"   Leads:     data/leads.csv")
    print(f"   Proposals: proposals/drafts/")
    print(f"   Sheet:     https://docs.google.com/spreadsheets/d/10tRBCuRl_T6_nmdN1ycHaSRmsK-7jGKLtbJewKAUz_I/edit")
    print(f"   Queue:     logs/email_queue.log")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
