"""
Full outreach pipeline orchestrator.

Pipeline stages:
  0. vibe_scraper.py   — Decision-maker leads via Vibe Prospecting MCP
  1. scraper.py        — Google Places fallback leads
  2. enricher.py       — Find emails, phones, LinkedIn
  3. researcher.py     — Research each prospect's website for pain points
  4. generator.py      — Generate personalized AI proposals (uses research + brain)
  5. reviewer.py       — Claude quality-reviews each proposal, flags weak ones
  6. generator.py      — Re-generate any proposals flagged as needs_revision
  7. blaster.py        — Send proposals via email + WhatsApp (WAHA + wacli)
  8. reply_tracker.py  — Check Gmail + WAHA inbox for replies
  9. converter.py      — Replied leads → meeting invite + PaperClip issue + n8n
  10. followup.py      — Send follow-ups to non-responders
  11. sheets_sync.py   — Sync funnel status to Google Sheet
  12. brain sync       — Store outcomes in hub brain for future learning

Modes:
  full          python3 orchestrator.py "Digital Agency Jakarta"
  dry-run       python3 orchestrator.py "Digital Agency Jakarta" --dry-run
  followup-only python3 orchestrator.py --followup-only
  enrich-only   python3 orchestrator.py --enrich-only
  sync-only     python3 orchestrator.py --sync-only
"""

import subprocess
import sys
from datetime import datetime

from config import _SCRIPTS_DIR


def run_step(script: str, label: str, args: list[str] | None = None) -> bool:
    if args is None:
        args = []
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {label}")
    print(f"{'=' * 60}")
    result = subprocess.run(
        ["python3", str(_SCRIPTS_DIR / script)] + args,
        capture_output=False,
    )
    if result.returncode != 0:
        print(
            f"⚠️  {script} exited with code {result.returncode}. Continuing pipeline..."
        )
    return result.returncode == 0


def _brain_sync() -> None:
    """Store all new outcomes in the hub brain for future proposal intelligence."""
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Syncing outcomes to hub brain")
    print(f"{'=' * 60}")
    try:
        from leads import load_leads
        import brain_client as brain

        if not brain.is_online():
            print("Hub brain offline — skipping brain sync.")
            return

        df = load_leads()
        if df is not None:
            brain.learn_batch_outcomes(df)
            stats = brain.stats()
            if stats:
                total = stats.get("total", stats.get("file_based_memories", "?"))
                print(f"[brain] Total memories in hub: {total}")
    except Exception as e:
        print(f"Brain sync error: {e}")


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

    # ── Sync only ──────────────────────────────────────────────────────────────
    if mode == "sync":
        run_step("sheets_sync.py", "Syncing funnel status to Google Sheet")
        _brain_sync()
        print("\n✅ Sync complete.")
        return

    # ── Followup only ──────────────────────────────────────────────────────────
    if mode == "followup":
        run_step("reply_tracker.py", "Checking for replies (Gmail + WAHA)")
        run_step("converter.py", "Converting replies → meeting invites")
        run_step("followup.py", "Sending follow-ups to non-responders")
        run_step("sheets_sync.py", "Syncing funnel status to Google Sheet")
        _brain_sync()
        print("\n✅ Follow-up cycle complete.")
        return

    # ── Enrich only ────────────────────────────────────────────────────────────
    if mode == "enrich":
        run_step("enricher.py", "Enriching contact info")
        run_step("researcher.py", "Researching prospect pain points")
        run_step("sheets_sync.py", "Syncing funnel status to Google Sheet")
        print("\n✅ Enrichment complete.")
        return

    # ── Full / dry-run pipeline ────────────────────────────────────────────────
    if not query:
        print("Usage: python3 1ai-engage/scripts/orchestrator.py <query> [--dry-run]")
        print(
            "  e.g. python3 1ai-engage/scripts/orchestrator.py 'Digital Agency in Jakarta'"
        )
        print("  e.g. python3 1ai-engage/scripts/orchestrator.py --followup-only")
        print("  e.g. python3 1ai-engage/scripts/orchestrator.py --sync-only")
        return

    industry, _, location_part = query.partition(" in ")
    location = location_part.strip() or "Jakarta, Indonesia"
    industry = industry.strip() or query

    dry = mode == "dry_run"
    print(f"\n🚀 Starting {'DRY RUN' if dry else 'FULL'} pipeline")
    print(f"   Industry: {industry}")
    print(f"   Location: {location}")

    # Step 0: Vibe Prospecting (decision-maker leads)
    run_step(
        "vibe_scraper.py",
        "Discovering decision-maker leads via Vibe Prospecting",
        [industry, location, "20"],
    )

    # Step 1: Google Places fallback
    run_step("scraper.py", "Scraping additional leads via Google Places", [query])

    # Step 2: Enrich
    run_step("enricher.py", "Enriching contact info")

    # Step 3: Research
    run_step("researcher.py", "Researching prospect pain points")

    # Step 4: Generate proposals (brain-informed)
    run_step("generator.py", "Generating personalized proposals")

    # Step 5: Review
    run_step("reviewer.py", "Reviewing proposal quality")

    # Step 6: Re-generate weak proposals
    run_step("generator.py", "Re-generating weak proposals")

    # Step 7: Send (skip in dry-run)
    if not dry:
        run_step("blaster.py", "Sending proposals via email + WhatsApp")

    # Step 8: Check replies
    run_step("reply_tracker.py", "Checking for replies (Gmail + WAHA)")

    # Step 9: Convert replied leads
    if not dry:
        run_step("converter.py", "Converting replies → meeting invites + PaperClip")

    # Step 10: Follow-ups
    run_step("followup.py", "Sending follow-ups to non-responders")

    # Step 11: Sheet sync
    run_step("sheets_sync.py", "Syncing funnel status to Google Sheet")

    # Step 12: Brain sync
    _brain_sync()

    print(f"\n{'=' * 60}")
    print("✅ Pipeline complete.")
    print(f"   Leads:     data/leads.csv")
    print(f"   Proposals: proposals/drafts/")
    print(
        f"   Sheet:     https://docs.google.com/spreadsheets/d/10tRBCuRl_T6_nmdN1ycHaSRmsK-7jGKLtbJewKAUz_I/edit"
    )
    print(f"   Queue:     logs/email_queue.log")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
