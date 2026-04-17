"""Proposal generator service - extracts business logic from scripts/generator.py."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

# Import brain_client from scripts (will be abstracted in Task 13)
_scripts_path = Path(__file__).parent.parent.parent.parent.parent / "scripts"
if str(_scripts_path) not in sys.path:
    sys.path.insert(0, str(_scripts_path))

import brain_client as _brain

logger = get_logger(__name__)

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


class GeneratorService:
    """Service for generating AI-powered proposals for leads.

    Uses brain integration to query past strategies and LLM chain
    (claude → gemini → oracle) for proposal generation.
    """

    def __init__(self, config: Settings):
        """Initialize generator service.

        Args:
            config: Application settings
        """
        self.config = config
        self.research_dir = Path(config.database.research_dir)
        self.proposals_dir = Path(config.database.proposals_dir)
        self.generator_model = config.llm.generator_model

    def load_research(self, lead_id: str, name: str) -> str:
        """Load the research brief for a lead if it exists.

        Args:
            lead_id: Lead ID
            name: Lead name (for filename)

        Returns:
            Research text or empty string if not found
        """
        safe_name = self._safe_filename(name)
        path = self.research_dir / f"{lead_id}_{safe_name}.txt"

        if path.exists():
            try:
                return path.read_text().strip()
            except Exception as e:
                logger.warning(f"Failed to read research file {path}: {e}")
                return ""
        return ""

    def get_capability_matrix(self, vertical: str) -> str:
        """Query Hub Brain for BerkahKarya capabilities.

        Falls back to hardcoded list if brain is unavailable.

        Args:
            vertical: Business vertical/type

        Returns:
            Capability matrix text
        """
        # Try to get strategy from brain
        matrix = _brain.get_strategy("berkahkarya_capabilities")
        if matrix:
            logger.debug("Got capability matrix from brain strategy")
            return matrix

        # Try brain search
        results = _brain.search(
            f"BerkahKarya services capabilities {vertical}", limit=5
        )
        if results:
            lines = []
            for r in results:
                content = r.get("content", "").strip()
                if content:
                    lines.append(f"- {content[:200]}")
            if lines:
                logger.debug(f"Got {len(lines)} capabilities from brain search")
                return "BerkahKarya capabilities (from brain):\n" + "\n".join(lines)

        logger.debug("Using fallback capability matrix")
        return _CAPABILITY_FALLBACK

    def build_prompt(
        self,
        lead: dict,
        research: str,
        capability_matrix: str,
        brain_context: str = "",
    ) -> Tuple[str, str]:
        """Build system and user prompts for proposal generation.

        No static boilerplate — everything is dynamic based on lead data
        and brain intelligence.

        Args:
            lead: Lead dictionary with contact info
            research: Research text for the lead
            capability_matrix: BerkahKarya capabilities
            brain_context: Additional context from brain

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        lead_name = self._parse_display_name(lead.get("displayName"))
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

        if website and not self._is_empty(website):
            user_parts.append(f"Website: {website}")
        if address and not self._is_empty(address):
            user_parts.append(f"Location: {address}")
        if email and not self._is_empty(email):
            user_parts.append(f"Email: {email}")
        if phone and not self._is_empty(phone):
            user_parts.append(f"Phone: {phone}")

        if research:
            user_parts.append(
                f"\nProspect Research (scraped from their website):\n{research}"
            )
        elif (
            csv_research
            and not self._is_empty(csv_research)
            and csv_research.lower() != "no_data"
        ):
            user_parts.append(f"\nProspect Research Summary: {csv_research}")

        if brain_context:
            user_parts.append(f"\n{brain_context}")

        if research or (csv_research and not self._is_empty(csv_research)):
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

    def generate_proposal(self, lead: dict, dry_run: bool = False) -> str:
        """Generate a proposal for a single lead.

        Args:
            lead: Lead dictionary with contact info
            dry_run: If True, print prompt instead of calling LLM

        Returns:
            Generated proposal text or empty string if all LLMs fail

        Raises:
            ExternalAPIError: If all LLM tools fail (only in non-dry-run mode)
        """
        lead_id = lead["id"]
        lead_name = self._parse_display_name(lead.get("displayName"))
        business_type = str(lead.get("type") or lead.get("primaryType") or "Business")

        logger.info(f"Generating proposal for {lead_name} ({business_type})")

        # Load research and brain context
        research = self.load_research(lead_id, lead_name)
        capability_matrix = self.get_capability_matrix(business_type)
        brain_context = _brain.get_strategy(business_type)

        # Build prompts
        system_prompt, user_prompt = self.build_prompt(
            lead, research, capability_matrix, brain_context
        )

        full_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"

        if dry_run:
            logger.info(f"[DRY-RUN] Would generate proposal for: {lead_name}")
            print("=" * 72)
            print(full_prompt)
            print("=" * 72)
            return ""

        # LLM chain: claude → gemini → oracle
        tools = [
            ("claude", ["claude", "-p", "--model", self.generator_model], True),
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
                    logger.info(f"Successfully generated proposal using {tool}")
                    return result.stdout

                logger.warning(
                    f"{tool} failed (exit {result.returncode}): "
                    f"{result.stderr.strip()[:120]}"
                )
            except subprocess.TimeoutExpired:
                logger.warning(f"{tool} timed out after 90s")
            except Exception as e:
                logger.warning(f"{tool} error: {e}")

        # All LLMs failed
        error_msg = f"All LLM tools failed for {lead_name}"
        logger.error(error_msg)
        raise ExternalAPIError(
            service="llm_chain",
            endpoint="/generate",
            status_code=0,
            reason=error_msg,
        )

    def save_proposal(self, lead_id: str, lead_name: str, proposal_text: str) -> Path:
        """Save proposal to file.

        Args:
            lead_id: Lead ID
            lead_name: Lead name (for filename)
            proposal_text: Proposal content

        Returns:
            Path to saved proposal file
        """
        safe_name = self._safe_filename(lead_name)
        path = self.proposals_dir / f"{lead_id}_{safe_name}.txt"

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write proposal
        path.write_text(proposal_text)
        logger.info(f"Saved proposal to {path}")

        return path

    @staticmethod
    def _is_empty(value) -> bool:
        """Check if a value is effectively missing.

        Args:
            value: Value to check

        Returns:
            True if value is None, NaN, empty string, 'nan', or 'none'
        """
        if value is None:
            return True
        s = str(value).strip().lower()
        return s in ("", "nan", "none")

    @staticmethod
    def _parse_display_name(raw) -> str:
        """Extract business name from raw displayName value.

        Handles both plain strings and stringified dicts.

        Args:
            raw: Raw displayName value

        Returns:
            Parsed business name or "Business" as fallback
        """
        if isinstance(raw, str) and raw.startswith("{"):
            try:
                import json

                return json.loads(raw.replace("'", '"')).get("text", "Business")
            except Exception:
                return "Business"
        if raw and not GeneratorService._is_empty(raw):
            return str(raw)
        return "Business"

    @staticmethod
    def _safe_filename(name: str) -> str:
        """Convert a name to a filesystem-safe string.

        Args:
            name: Original name

        Returns:
            Filesystem-safe name (alphanumeric + underscores)
        """
        return "".join(c if c.isalnum() else "_" for c in str(name))
