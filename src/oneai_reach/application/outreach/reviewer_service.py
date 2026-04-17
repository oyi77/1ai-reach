"""Proposal reviewer service - extracts business logic from scripts/reviewer.py."""

import subprocess
import sys
from typing import Dict, Optional

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

# Pass threshold: proposals scoring below this need revision
PASS_THRESHOLD = 6


class ReviewerService:
    """Service for reviewing AI-generated proposals using Claude.

    Reviews proposals on 5 criteria:
    1. Personalization (references specific business details)
    2. Pain points (addresses real prospect problems)
    3. Value proposition (clear and relevant)
    4. CTA (specific, low-friction, compelling)
    5. Tone (professional, warm, not spammy)

    Scores proposals 1-10 and marks as PASS/FAIL based on threshold.
    """

    def __init__(self, config: Settings):
        """Initialize reviewer service.

        Args:
            config: Application settings
        """
        self.config = config
        self.reviewer_model = config.llm.reviewer_model
        self.pass_threshold = PASS_THRESHOLD

    def build_review_prompt(self, name: str, proposal: str, research: str) -> str:
        """Build the review prompt for Claude.

        Args:
            name: Prospect name
            proposal: Proposal text to review
            research: Research brief for the prospect

        Returns:
            Formatted review prompt
        """
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

    def call_claude(self, prompt: str) -> Optional[str]:
        """Call Claude CLI to review proposal.

        Args:
            prompt: Review prompt

        Returns:
            Claude's response or None if call fails

        Raises:
            ExternalAPIError: If Claude call fails
        """
        try:
            result = subprocess.run(
                ["claude", "-p", "--model", self.reviewer_model],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                logger.debug("Successfully called Claude for review")
                return result.stdout.strip()

            logger.warning(
                f"Claude returned non-zero exit code: {result.returncode}, "
                f"stderr: {result.stderr.strip()[:120]}"
            )
            raise ExternalAPIError(
                service="claude",
                endpoint="/review",
                status_code=result.returncode,
                reason=result.stderr.strip()[:200] or "Empty response",
            )

        except subprocess.TimeoutExpired:
            logger.error("Claude review timed out after 60s")
            raise ExternalAPIError(
                service="claude",
                endpoint="/review",
                status_code=0,
                reason="Request timed out after 60s",
            )
        except FileNotFoundError:
            logger.error("Claude CLI not found in PATH")
            raise ExternalAPIError(
                service="claude",
                endpoint="/review",
                status_code=0,
                reason="Claude CLI not installed or not in PATH",
            )
        except Exception as e:
            logger.error(f"Claude review error: {e}")
            raise ExternalAPIError(
                service="claude",
                endpoint="/review",
                status_code=0,
                reason=str(e),
            )

    def parse_review_output(self, output: str) -> Dict[str, any]:
        """Parse Claude's review output into structured data.

        Args:
            output: Raw Claude output

        Returns:
            Dictionary with score, verdict, issues, and suggestion
        """
        score = 0
        verdict = "FAIL"
        issues = []
        suggestion = ""

        for line in output.splitlines():
            line = line.strip()
            if line.startswith("SCORE:"):
                try:
                    score = int(line.split(":")[1].strip().split("/")[0])
                except Exception as e:
                    logger.warning(f"Failed to parse score from line '{line}': {e}")
            elif line.startswith("VERDICT:"):
                verdict = line.split(":", 1)[1].strip()
            elif line.startswith("ISSUES:"):
                raw = line.split(":", 1)[1].strip()
                issues = [
                    i.strip() for i in raw.split(",") if i.strip().lower() != "none"
                ]
            elif line.startswith("SUGGESTION:"):
                suggestion = line.split(":", 1)[1].strip()

        return {
            "score": score,
            "verdict": verdict,
            "issues": issues,
            "suggestion": suggestion,
        }

    def review_proposal(
        self, index: int, name: str, proposal: str, research: str
    ) -> Dict[str, any]:
        """Review a single proposal using Claude.

        Args:
            index: Lead index (for logging)
            name: Prospect name
            proposal: Proposal text to review
            research: Research brief for the prospect

        Returns:
            Dictionary with score, verdict, issues, and suggestion
        """
        logger.info(f"Reviewing proposal for {name} (index {index})")

        prompt = self.build_review_prompt(name, proposal, research)

        try:
            output = self.call_claude(prompt)
            if not output:
                logger.error(f"Empty response from Claude for {name}")
                return {
                    "score": 0,
                    "verdict": "ERROR",
                    "issues": ["reviewer failed - empty response"],
                    "suggestion": "",
                }

            review = self.parse_review_output(output)
            logger.info(
                f"Review complete for {name}: {review['verdict']} "
                f"(score: {review['score']}/10)"
            )
            return review

        except ExternalAPIError as e:
            logger.error(f"Review failed for {name}: {e}")
            return {
                "score": 0,
                "verdict": "ERROR",
                "issues": [f"reviewer failed - {e.message}"],
                "suggestion": "",
            }

    def is_passing(self, review: Dict[str, any]) -> bool:
        """Check if a review passes the threshold.

        Args:
            review: Review dictionary with score and verdict

        Returns:
            True if proposal passes (score >= threshold or verdict is PASS)
        """
        score = review.get("score", 0)
        verdict = review.get("verdict", "FAIL")

        return verdict == "PASS" or score >= self.pass_threshold

    def format_issues(self, review: Dict[str, any]) -> str:
        """Format issues list as a string.

        Args:
            review: Review dictionary with issues list

        Returns:
            Semicolon-separated issues or "none"
        """
        issues = review.get("issues", [])
        if not issues:
            return "none"
        return "; ".join(issues)
