"""Proposal validator service - quality validation logic.

Pure business logic for validating proposal quality based on
scoring thresholds and business rules.
"""

from typing import Dict, Optional

from oneai_reach.domain.models.proposal import Proposal


class ProposalValidator:
    """Validate proposal quality against business rules.

    Business rules:
    - Pass threshold: 6/10 (proposals scoring below need revision)
    - High quality threshold: 7/10 (ready for immediate sending)
    - Minimum word count: 50 words
    - Maximum word count: 500 words (to avoid overly long proposals)
    """

    # Thresholds
    PASS_THRESHOLD = 6
    HIGH_QUALITY_THRESHOLD = 7
    MIN_WORD_COUNT = 50
    MAX_WORD_COUNT = 500

    def __init__(self, pass_threshold: int = PASS_THRESHOLD):
        """Initialize validator with custom threshold.

        Args:
            pass_threshold: Minimum score for passing (default: 6)
        """
        self.pass_threshold = pass_threshold

    def is_passing(self, score: int) -> bool:
        """Check if a score passes the quality threshold.

        Args:
            score: Proposal score (1-10 scale)

        Returns:
            True if score >= threshold

        Examples:
            >>> validator = ProposalValidator()
            >>> validator.is_passing(7)
            True
            >>> validator.is_passing(5)
            False
            >>> validator.is_passing(6)
            True
        """
        return score >= self.pass_threshold

    def is_high_quality(self, score: int) -> bool:
        """Check if a score indicates high quality.

        Args:
            score: Proposal score (1-10 scale)

        Returns:
            True if score >= high quality threshold (7)
        """
        return score >= self.HIGH_QUALITY_THRESHOLD

    def validate_proposal(self, proposal: Proposal) -> Dict[str, any]:
        """Validate a proposal against all business rules.

        Args:
            proposal: Proposal entity to validate

        Returns:
            Dictionary with:
                - valid: bool (passes all checks)
                - passing: bool (score >= threshold)
                - high_quality: bool (score >= 7)
                - issues: list of validation issues
                - score: proposal score

        Examples:
            >>> validator = ProposalValidator()
            >>> proposal = Proposal(lead_id="1", content="Short", score=8.0)
            >>> result = validator.validate_proposal(proposal)
            >>> result["passing"]
            True
            >>> result["issues"]
            ['Content too short (1 words, minimum 50)']
        """
        issues = []

        # Check score
        score = proposal.score
        if score is None:
            issues.append("Proposal has not been scored")
            passing = False
            high_quality = False
        else:
            passing = self.is_passing(int(score))
            high_quality = self.is_high_quality(int(score))

            if not passing:
                issues.append(
                    f"Score too low ({score}/10, minimum {self.pass_threshold})"
                )

        # Check word count
        word_count = proposal.word_count
        if word_count < self.MIN_WORD_COUNT:
            issues.append(
                f"Content too short ({word_count} words, minimum {self.MIN_WORD_COUNT})"
            )
        elif word_count > self.MAX_WORD_COUNT:
            issues.append(
                f"Content too long ({word_count} words, maximum {self.MAX_WORD_COUNT})"
            )

        # Check if content is empty
        if not proposal.content.strip():
            issues.append("Content is empty")

        # Valid if no issues
        valid = len(issues) == 0

        return {
            "valid": valid,
            "passing": passing if score is not None else False,
            "high_quality": high_quality if score is not None else False,
            "issues": issues,
            "score": score,
        }

    def needs_revision(self, proposal: Proposal) -> bool:
        """Check if proposal needs revision.

        Args:
            proposal: Proposal entity

        Returns:
            True if proposal fails validation or has low score
        """
        validation = self.validate_proposal(proposal)
        return not validation["passing"] or not validation["valid"]

    def get_revision_priority(self, proposal: Proposal) -> str:
        """Get revision priority level.

        Args:
            proposal: Proposal entity

        Returns:
            Priority level: "critical", "high", "medium", "low", or "none"

        Priority levels:
            - critical: No score or empty content
            - high: Score < 4 or major validation issues
            - medium: Score 4-5
            - low: Score 6 but has minor issues
            - none: Score >= 7 and valid
        """
        validation = self.validate_proposal(proposal)
        score = proposal.score

        # Critical: no score or empty content
        if score is None or not proposal.content.strip():
            return "critical"

        # High: very low score or multiple issues
        if score < 4 or len(validation["issues"]) > 2:
            return "high"

        # Medium: low score
        if score < 6:
            return "medium"

        # Low: passing but has issues
        if validation["issues"]:
            return "low"

        # None: high quality
        return "none"

    def format_validation_report(self, proposal: Proposal) -> str:
        """Format validation results as human-readable report.

        Args:
            proposal: Proposal entity

        Returns:
            Formatted validation report string
        """
        validation = self.validate_proposal(proposal)

        lines = []
        lines.append(f"Proposal Validation Report")
        lines.append(f"=" * 40)
        lines.append(f"Lead ID: {proposal.lead_id}")
        lines.append(f"Score: {validation['score']}/10")
        lines.append(f"Status: {'✅ PASS' if validation['passing'] else '❌ FAIL'}")
        lines.append(
            f"Quality: {'⭐ HIGH' if validation['high_quality'] else 'STANDARD'}"
        )
        lines.append(f"Word Count: {proposal.word_count}")

        if validation["issues"]:
            lines.append(f"\nIssues:")
            for issue in validation["issues"]:
                lines.append(f"  - {issue}")
        else:
            lines.append(f"\n✅ No issues found")

        priority = self.get_revision_priority(proposal)
        if priority != "none":
            lines.append(f"\nRevision Priority: {priority.upper()}")

        return "\n".join(lines)
