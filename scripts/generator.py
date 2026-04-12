"""
AI proposal generator.

For each lead with an email:
  1. Loads prospect research brief (from data/research/ if available)
  2. Passes research + lead info to Claude for a truly personalized proposal
  3. Falls back to gemini → oracle if Claude unavailable
  4. Skips lead (logs error) if all LLMs fail — no template fallback
"""

import os
import subprocess
import sys

from leads import load_leads
from utils import parse_display_name, draft_path, safe_filename, is_empty

from config import PROPOSALS_DIR as _PROPOSALS_DIR, RESEARCH_DIR as _RESEARCH_DIR
import brain_client as _brain

PROPOSALS_DIR = str(_PROPOSALS_DIR)
RESEARCH_DIR = str(_RESEARCH_DIR)


def _load_research(index: int, name: str) -> str:
    """Load the research brief for this lead if it exists."""
    path = os.path.join(RESEARCH_DIR, f"{index}_{safe_filename(name)}.txt")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return ""


def _build_prompt(
    lead_name: str,
    lead_business: str,
    research: str,
    csv_research: str,
    brain_context: str = "",
) -> str:
    research_section = ""
    if research:
        research_section = (
            f"\nProspect Research (scraped from their website):\n{research}\n"
        )
    elif (
        csv_research
        and not is_empty(csv_research)
        and csv_research.lower() != "no_data"
    ):
        research_section = f"\nProspect Research Summary: {csv_research}\n"

    brain_section = f"\n{brain_context}\n" if brain_context else ""

    pain_instruction = (
        "Use the research above to write a HIGHLY PERSONALIZED proposal. "
        "Reference their specific services, observed gaps, or tech stack. "
        "Do NOT write generic filler."
        if research_section
        else "Write a proposal specific to their business type. "
        "Reference challenges common to this niche."
    )

    return (
        f"You are writing a cold outreach email and WhatsApp message on behalf of Vilona from BerkahKarya.\n\n"
        f"BerkahKarya offers: AI Automation, Digital Marketing, and Software Development.\n"
        f"Goal: Convince {lead_name} to book a 15-minute discovery call.\n\n"
        f"Prospect: {lead_name}\n"
        f"Business Type: {lead_business}\n"
        f"{research_section}"
        f"{brain_section}\n"
        f"Instructions:\n"
        f"- {pain_instruction}\n"
        f"- The email must open with a specific observation about their business (not 'I hope this email finds you well').\n"
        f"- Mention 1-2 concrete benefits of AI automation relevant to their niche.\n"
        f"- End with a low-friction CTA: offer a 15-minute call or a free audit.\n"
        f"- The WhatsApp message must be SHORT (3-4 sentences), casual, in Indonesian (Bahasa Indonesia).\n"
        f"- The WhatsApp message should feel human, not like a sales pitch.\n\n"
        f"Output format (use these exact separators, nothing before or after):\n"
        f"---PROPOSAL---\n"
        f"[professional email body in English]\n"
        f"---WHATSAPP---\n"
        f"[short casual WhatsApp message in Indonesian]"
    )


def generate_proposal(
    index: int, lead_name: str, lead_business: str, csv_research: str = ""
) -> str:
    research = _load_research(index, lead_name)
    brain_context = _brain.get_strategy(lead_business)
    prompt = _build_prompt(
        lead_name, lead_business, research, csv_research, brain_context
    )

    tools = [
        ("claude", ["claude", "-p", "--model", "sonnet"], True),
        ("gemini", ["gemini", "ask", prompt], False),
        ("oracle", ["oracle", prompt], False),
    ]

    for tool, cmd, use_stdin in tools:
        try:
            kwargs = dict(capture_output=True, text=True, timeout=90)
            if use_stdin:
                kwargs["input"] = prompt
            result = subprocess.run(cmd, **kwargs)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
            print(
                f"{tool} failed (exit {result.returncode}): {result.stderr.strip()[:120]}",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"{tool} error: {e}", file=sys.stderr)

    print(f"ERROR: All LLM tools failed for {lead_name}. Skipping.", file=sys.stderr)
    return ""


def process_proposals() -> None:
    df = load_leads()
    if df is None:
        return
    os.makedirs(PROPOSALS_DIR, exist_ok=True)

    generated = skipped = 0
    for index, row in df.iterrows():
        name = parse_display_name(row.get("displayName"))
        status = str(row.get("status") or "")

        # Skip already-processed leads (reviewed, contacted, replied, etc.)
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

        # Only generate for leads with email (so we can actually reach them)
        email = str(row.get("email") or "").strip()
        if is_empty(email):
            skipped += 1
            continue

        # Skip if draft already exists and lead has no needs_revision flag
        path = draft_path(index, name)
        if os.path.exists(path) and status != "needs_revision":
            skipped += 1
            continue

        business = str(row.get("type") or row.get("primaryType") or "Business")
        csv_research = str(row.get("research") or "")

        print(f"Generating proposal for {name} ({business})...")
        proposal_text = generate_proposal(index, name, business, csv_research)
        if not proposal_text:
            continue

        with open(path, "w") as f:
            f.write(proposal_text)
        generated += 1

    print(f"\nGeneration complete. {generated} generated, {skipped} skipped.")


if __name__ == "__main__":
    process_proposals()
