"""
Proposal quality reviewer.

Reviews each generated draft proposal using Claude.
Checks: personalization, specific pain points, clear CTA, professional tone.
Marks lead status as 'reviewed' if passed, 'needs_revision' if failed.
Optionally regenerates weak proposals in-place.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from leads import load_leads, save_leads
from utils import parse_display_name, draft_path
from oneai_reach.config.settings import get_settings
from oneai_reach.application.outreach.reviewer_service import ReviewerService

PASS_THRESHOLD = 6


def process_reviews(regenerate_weak: bool = True) -> None:
    settings = get_settings()
    service = ReviewerService(settings)

    df = load_leads()
    if df is None:
        return

    for col in ("status", "review_score", "review_issues"):
        if col not in df.columns:
            df[col] = None
        df[col] = df[col].astype(object)

    passed = failed = skipped = 0

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

        path = draft_path(index, name)
        if not os.path.exists(path):
            continue

        with open(path) as f:
            content = f.read()

        proposal = (
            content.split("---WHATSAPP---")[0].replace("---PROPOSAL---", "").strip()
        )
        research = str(row.get("research") or "No research available.")

        print(f"Reviewing: {name}...")
        review = service.review_proposal(index, name, proposal, research)

        score = review["score"]
        issues = service.format_issues(review)

        df.at[index, "review_score"] = score
        df.at[index, "review_issues"] = issues

        if service.is_passing(review):
            df.at[index, "status"] = "reviewed"
            print(f"  ✅ PASS ({score}/10)")
            passed += 1
        else:
            print(f"  ❌ FAIL ({score}/10) — {issues}")
            if regenerate_weak and review.get("suggestion"):
                print(f"  Suggestion: {review['suggestion']}")
            df.at[index, "status"] = "needs_revision"
            failed += 1

    save_leads(df)
    print(
        f"\nReview complete: {passed} passed, {failed} need revision, {skipped} skipped."
    )


if __name__ == "__main__":
    process_reviews()
