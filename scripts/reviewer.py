"""
Proposal quality reviewer.

Reviews each generated draft proposal using Claude.
Checks: personalization, specific pain points, clear CTA, professional tone.
Marks lead status as 'reviewed' if passed, 'needs_revision' if failed.
Optionally regenerates weak proposals in-place.
"""

import os
import subprocess
import sys

from leads import load_leads, save_leads
from utils import parse_display_name, draft_path
from config import REVIEWER_MODEL

PASS_THRESHOLD = 6  # out of 10 — below this, regenerate


def _review_prompt(name: str, proposal: str, research: str) -> str:
    return (
        f"You are a senior B2B sales consultant reviewing a cold outreach email proposal.\n\n"
        f"Prospect: {name}\n"
        f"Research brief:\n{research}\n\n"
        f"--- PROPOSAL TO REVIEW ---\n{proposal}\n--- END PROPOSAL ---\n\n"
        f"Score this proposal from 1-10 on these criteria:\n"
        f"1. Personalization: Does it reference specifics about this business (not generic)?\n"
        f"2. Pain points: Does it address a real problem this prospect likely has?\n"
        f"3. Value proposition: Is BerkahKarya's value clearly stated and relevant?\n"
        f"4. CTA: Is the call to action specific, low-friction, and compelling?\n"
        f"5. Tone: Professional, warm, not spammy?\n\n"
        f"Respond in exactly this format:\n"
        f"SCORE: X/10\n"
        f"VERDICT: PASS or FAIL\n"
        f"ISSUES: [comma-separated list of issues, or 'none']\n"
        f"SUGGESTION: [one specific improvement to make it better]"
    )


def _call_claude(prompt: str) -> str:
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", REVIEWER_MODEL],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        print(f"Claude reviewer error: {e}", file=sys.stderr)
    return ""


def _parse_review(output: str) -> dict:
    score = 0
    verdict = "FAIL"
    issues = []
    suggestion = ""

    for line in output.splitlines():
        if line.startswith("SCORE:"):
            try:
                score = int(line.split(":")[1].strip().split("/")[0])
            except Exception:
                pass
        elif line.startswith("VERDICT:"):
            verdict = line.split(":")[1].strip()
        elif line.startswith("ISSUES:"):
            raw = line.split(":", 1)[1].strip()
            issues = [i.strip() for i in raw.split(",") if i.strip().lower() != "none"]
        elif line.startswith("SUGGESTION:"):
            suggestion = line.split(":", 1)[1].strip()

    return {
        "score": score,
        "verdict": verdict,
        "issues": issues,
        "suggestion": suggestion,
    }


def review_proposal(index: int, name: str, proposal: str, research: str) -> dict:
    prompt = _review_prompt(name, proposal, research)
    output = _call_claude(prompt)
    if not output:
        return {
            "score": 0,
            "verdict": "ERROR",
            "issues": ["reviewer failed"],
            "suggestion": "",
        }
    return _parse_review(output)


def process_reviews(regenerate_weak: bool = True) -> None:
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

        # Skip already reviewed or contacted leads
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
        review = review_proposal(index, name, proposal, research)

        score = review["score"]
        verdict = review["verdict"]
        issues = "; ".join(review["issues"]) if review["issues"] else "none"

        df.at[index, "review_score"] = score
        df.at[index, "review_issues"] = issues

        if verdict == "PASS" or score >= PASS_THRESHOLD:
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
