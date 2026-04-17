"""Lead scoring service - calculates lead quality scores.

Pure business logic for scoring leads based on data completeness,
engagement signals, and funnel progression.
"""

from typing import Optional

from oneai_reach.domain.models.lead import Lead, LeadStatus


class LeadScoringService:
    """Calculate lead quality scores on a 0-100 scale.

    Scoring algorithm:
    - Base score: 20 points (every lead starts here)
    - Contact info: +15 points for email, +15 for phone
    - Web presence: +10 for website, +10 for LinkedIn
    - Research: +10 if research completed
    - Engagement: +20 for replied, +30 for meeting booked
    - Negative: -50 for cold/lost/unsubscribed

    Maximum possible score: 100
    Minimum possible score: 0
    """

    def calculate_score(self, lead: Lead) -> int:
        """Calculate quality score for a lead.

        Args:
            lead: Lead entity to score

        Returns:
            Integer score from 0-100

        Examples:
            >>> service = LeadScoringService()
            >>> lead = Lead(id="1", status=LeadStatus.NEW)
            >>> service.calculate_score(lead)
            20
            >>> lead.email = "test@example.com"
            >>> lead.phone = "+628123456789"
            >>> service.calculate_score(lead)
            50
        """
        score = 20  # Base score

        # Contact information (30 points max)
        if lead.email:
            score += 15
        if lead.phone or lead.internationalPhoneNumber:
            score += 15

        # Web presence (20 points max)
        if lead.websiteUri:
            score += 10
        if lead.linkedin:
            score += 10

        # Research completed (10 points)
        if lead.research:
            score += 10

        # Engagement signals (30 points max)
        if lead.status == LeadStatus.REPLIED:
            score += 20
        elif lead.status == LeadStatus.MEETING_BOOKED:
            score += 30
        elif lead.status == LeadStatus.WON:
            score += 30

        # Negative signals (-50 points)
        if lead.status in (LeadStatus.COLD, LeadStatus.LOST, LeadStatus.UNSUBSCRIBED):
            score -= 50

        # Clamp to 0-100 range
        return max(0, min(100, score))

    def get_score_category(self, score: int) -> str:
        """Categorize score into quality tiers.

        Args:
            score: Lead score (0-100)

        Returns:
            Category string: "hot", "warm", "cold", or "dead"

        Categories:
            - hot: 70-100 (high quality, ready to contact)
            - warm: 50-69 (medium quality, needs enrichment)
            - cold: 30-49 (low quality, needs more data)
            - dead: 0-29 (very low quality or disqualified)
        """
        if score >= 70:
            return "hot"
        elif score >= 50:
            return "warm"
        elif score >= 30:
            return "cold"
        else:
            return "dead"

    def is_ready_for_outreach(self, lead: Lead) -> bool:
        """Check if lead has minimum data quality for outreach.

        Args:
            lead: Lead entity to check

        Returns:
            True if lead is ready for outreach (score >= 50)
        """
        score = self.calculate_score(lead)
        return score >= 50
