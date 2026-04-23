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
import subprocess
import sys

from leads import load_leads
from utils import parse_display_name, draft_path, safe_filename, is_empty
from config import (
    PROPOSALS_DIR as _PROPOSALS_DIR,
    RESEARCH_DIR as _RESEARCH_DIR,
    GENERATOR_MODEL,
)
import brain_client as _brain
import state_manager as _sm

PROPOSALS_DIR = str(_PROPOSALS_DIR)
RESEARCH_DIR = str(_RESEARCH_DIR)

_CAPABILITY_FALLBACK = (
    "BerkahKarya capabilities:\n"
    "- Custom web & mobile app development (Next.js, React Native, Flutter)\n"
    "- AI-powered automation workflows (n8n, Make, custom agents)\n"
    "- WhatsApp Business API integration & chatbot development\n"
    "- Digital marketing: SEO, Google Ads, Meta Ads, TikTok Ads\n"
    "- Social media management & content production\n"
    "- Branding, UI/UX design, and design systems\n"
    "- E-commerce solutions (Shopify, WooCommerce, custom)\n"
    "- Landing page & conversion rate optimization\n"
    "- Data analytics dashboards & BI reporting\n"
    "- IT consulting & digital transformation roadmaps"
)


def _load_research(lead_id, name: str) -> str:
    """Load the research brief for this lead if it exists."""
    path = os.path.join(RESEARCH_DIR, f"{lead_id}_{safe_filename(name)}.txt")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return ""


def _get_capability_matrix(vertical: str) -> str:
    """Query Hub Brain for BerkahKarya capabilities, fall back to hardcoded list."""
    matrix = _brain.get_strategy("berkahkarya_capabilities")
    if matrix:
        return matrix

    results = _brain.search(f"BerkahKarya services capabilities {vertical}", limit=5)
    if results:
        lines = []
        for r in results:
            content = r.get("content", "").strip()
            if content:
                lines.append(f"- {content[:200]}")
        if lines:
            return "BerkahKarya capabilities (from brain):\n" + "\n".join(lines)

    return _CAPABILITY_FALLBACK


def _build_prompt(
    lead: dict,
    research: str,
    capability_matrix: str,
    brain_context: str = "",
) -> tuple:
    """
    Build system + user prompt pair. Returns (system_prompt, user_prompt).
    No static boilerplate — everything is dynamic based on lead data + brain intelligence.
    """
    lead_name = parse_display_name(lead.get("displayName"))
    business_type = str(lead.get("type") or lead.get("primaryType") or "Business")
    website = str(lead.get("websiteUri") or lead.get("website") or "")
    email = str(lead.get("email") or "")
    phone = str(lead.get("phone") or lead.get("internationalPhoneNumber") or "")
    address = str(lead.get("formattedAddress") or "")
    csv_research = str(lead.get("research") or "")

    system_prompt = (
        "You are a senior Solution Architect at BerkahKarya, a technology and growth partner.\n\n"
        f"Available capability matrix:\n{capability_matrix}\n\n"
        "Your task: Based on the prospect's research data below, INVENT a specific, tailored digital solution.\n"
        "DO NOT use generic phrases like 'we are a digital agency' or 'we help businesses grow'.\n"
        "Instead, identify the exact gap or opportunity this prospect has, and propose 1-2 concrete solutions.\n"
        "Be creative — you may bundle or combine services from the capability matrix.\n"
        "Sign the email as Vilona from BerkahKarya."
    )

    user_parts = [
        f"Prospect: {lead_name}",
        f"Business Type: {business_type}",
    ]
    if website and not is_empty(website):
        user_parts.append(f"Website: {website}")
    if address and not is_empty(address):
        user_parts.append(f"Location: {address}")
    if email and not is_empty(email):
        user_parts.append(f"Email: {email}")
    if phone and not is_empty(phone):
        user_parts.append(f"Phone: {phone}")

    if research:
        user_parts.append(
            f"\nProspect Research (scraped from their website):\n{research}"
        )
    elif (
        csv_research
        and not is_empty(csv_research)
        and csv_research.lower() != "no_data"
    ):
        user_parts.append(f"\nProspect Research Summary: {csv_research}")

    if brain_context:
        user_parts.append(f"\n{brain_context}")

    if research or (csv_research and not is_empty(csv_research)):
        pain_instruction = (
            "Use the research above to write a HIGHLY PERSONALIZED proposal. "
            "Reference their specific services, observed gaps, or tech stack. "
            "Do NOT write generic filler."
        )
    else:
        pain_instruction = (
            "Write a proposal specific to their business type. "
            "Reference challenges common to this niche."
        )

    user_parts.append(
        f"\nInstructions:\n"
        f"- {pain_instruction}\n"
        f"- The email must open with a specific observation about their business "
        f"(not 'I hope this email finds you well').\n"
        f"- Propose 1-2 concrete solutions from the capability matrix — name the deliverables.\n"
        f"- Mention a specific ROI or metric where possible (e.g., '30% more leads', "
        f"'cut response time by 5x').\n"
        f"- End with a low-friction CTA: offer a 15-minute call or a free audit.\n"
        f"- The WhatsApp message must be SHORT (3-4 sentences), casual, in Indonesian (Bahasa Indonesia).\n"
        f"- The WhatsApp message should feel human, not like a sales pitch.\n\n"
        f"Output format (use these exact separators, nothing before or after):\n"
        f"---PROPOSAL---\n"
        f"[professional email body in English]\n"
        f"---WHATSAPP---\n"
        f"[short casual WhatsApp message in Indonesian]"
    )

    user_prompt = "\n".join(user_parts)
    return system_prompt, user_prompt


def generate_proposal(lead: dict, dry_run: bool = False) -> str:
    """Generate a proposal for a single lead. Returns proposal text or ''."""
    lead_id = lead["id"]
    lead_name = parse_display_name(lead.get("displayName"))
    business_type = str(lead.get("type") or lead.get("primaryType") or "Business")

    research = _load_research(lead_id, lead_name)
    capability_matrix = _get_capability_matrix(business_type)
    brain_context = _brain.get_strategy(business_type)

    system_prompt, user_prompt = _build_prompt(
        lead, research, capability_matrix, brain_context
    )

    full_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"

    if dry_run:
        print(f"[DRY-RUN] Would generate proposal for: {lead_name}")
        print("=" * 72)
        print(full_prompt)
        print("=" * 72)
        return ""

    tools = [
        ("claude", ["claude", "-p", "--model", GENERATOR_MODEL], True),
        ("gemini", ["gemini", "ask", full_prompt], False),
        ("oracle", ["oracle", full_prompt], False),
    ]

    for tool, cmd, use_stdin in tools:
        try:
            kwargs = dict(capture_output=True, text=True, timeout=90)
            if use_stdin:
                kwargs["input"] = full_prompt
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


def _process_single_lead(lead: dict, dry_run: bool = False) -> bool:
    """Process one lead. Returns True if proposal was generated/saved."""
    lead_id = lead["id"]
    lead_name = parse_display_name(lead.get("displayName"))
    business_type = str(lead.get("type") or lead.get("primaryType") or "Business")

    print(f"Generating proposal for {lead_name} ({business_type})...")
    proposal_text = generate_proposal(lead, dry_run=dry_run)

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

    if lead_id:
        lead = _sm.get_lead_by_id(lead_id)
        if not lead:
            print(f"ERROR: Lead {lead_id} not found in database.", file=sys.stderr)
            sys.exit(1)
        _process_single_lead(lead, dry_run=dry_run)
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
            ok = _process_single_lead(lead, dry_run=dry_run)
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

        email = str(row.get("email") or "").strip()
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
        proposal_text = generate_proposal(lead_dict, dry_run=dry_run)

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
