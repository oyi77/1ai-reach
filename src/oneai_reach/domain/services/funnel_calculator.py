"""Funnel calculator service - funnel metrics calculation.

Pure business logic for calculating funnel stage metrics,
conversion rates, and pipeline health indicators.
"""

from typing import Dict, List

from oneai_reach.domain.models.lead import Lead, LeadStatus


class FunnelCalculator:
    """Calculate funnel metrics and conversion rates.

    Provides analytics for:
    - Stage distribution (count per funnel stage)
    - Conversion rates (stage-to-stage progression)
    - Pipeline health (velocity, bottlenecks)
    - Win/loss analysis
    """

    # Funnel stages in order
    FUNNEL_STAGES = [
        LeadStatus.NEW,
        LeadStatus.ENRICHED,
        LeadStatus.DRAFT_READY,
        LeadStatus.NEEDS_REVISION,
        LeadStatus.REVIEWED,
        LeadStatus.CONTACTED,
        LeadStatus.FOLLOWED_UP,
        LeadStatus.REPLIED,
        LeadStatus.MEETING_BOOKED,
        LeadStatus.WON,
        LeadStatus.LOST,
        LeadStatus.COLD,
        LeadStatus.UNSUBSCRIBED,
    ]

    def calculate_metrics(self, leads: List[Lead]) -> Dict[str, any]:
        """Calculate comprehensive funnel metrics.

        Args:
            leads: List of lead entities

        Returns:
            Dictionary with:
                - total: total lead count
                - by_stage: count per stage
                - conversion_rates: stage-to-stage conversion %
                - win_rate: percentage of leads that won
                - loss_rate: percentage of leads that lost
                - active_pipeline: count of leads in active stages

        Examples:
            >>> calculator = FunnelCalculator()
            >>> leads = [
            ...     Lead(id="1", status=LeadStatus.NEW),
            ...     Lead(id="2", status=LeadStatus.CONTACTED),
            ...     Lead(id="3", status=LeadStatus.WON),
            ... ]
            >>> metrics = calculator.calculate_metrics(leads)
            >>> metrics["total"]
            3
            >>> metrics["win_rate"]
            33.33
        """
        if not leads:
            return self._empty_metrics()

        # Count by stage
        by_stage = self._count_by_stage(leads)

        # Calculate conversion rates
        conversion_rates = self._calculate_conversion_rates(by_stage)

        # Calculate win/loss rates
        total = len(leads)
        won = by_stage.get(LeadStatus.WON, 0)
        lost = by_stage.get(LeadStatus.LOST, 0) + by_stage.get(LeadStatus.COLD, 0)

        win_rate = round((won / total * 100), 2) if total > 0 else 0.0
        loss_rate = round((lost / total * 100), 2) if total > 0 else 0.0

        # Active pipeline (not won/lost/cold/unsubscribed)
        active_stages = [
            LeadStatus.NEW,
            LeadStatus.ENRICHED,
            LeadStatus.DRAFT_READY,
            LeadStatus.NEEDS_REVISION,
            LeadStatus.REVIEWED,
            LeadStatus.CONTACTED,
            LeadStatus.FOLLOWED_UP,
            LeadStatus.REPLIED,
            LeadStatus.MEETING_BOOKED,
        ]
        active_pipeline = sum(by_stage.get(stage, 0) for stage in active_stages)

        return {
            "total": total,
            "by_stage": {
                stage.value: by_stage.get(stage, 0) for stage in self.FUNNEL_STAGES
            },
            "conversion_rates": conversion_rates,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "active_pipeline": active_pipeline,
        }

    def _count_by_stage(self, leads: List[Lead]) -> Dict[LeadStatus, int]:
        """Count leads by stage.

        Args:
            leads: List of leads

        Returns:
            Dictionary mapping stage to count
        """
        counts = {}
        for lead in leads:
            status = lead.status
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _calculate_conversion_rates(
        self, by_stage: Dict[LeadStatus, int]
    ) -> Dict[str, float]:
        """Calculate stage-to-stage conversion rates.

        Args:
            by_stage: Count by stage

        Returns:
            Dictionary with conversion rate percentages
        """
        rates = {}

        # Key conversion points
        total_leads = sum(by_stage.values())
        if total_leads == 0:
            return rates

        # Enrichment rate (new -> enriched)
        new_count = by_stage.get(LeadStatus.NEW, 0)
        enriched_count = by_stage.get(LeadStatus.ENRICHED, 0)
        if new_count + enriched_count > 0:
            rates["enrichment_rate"] = round(
                (enriched_count / (new_count + enriched_count) * 100), 2
            )

        # Review pass rate (draft_ready -> reviewed)
        draft_count = by_stage.get(LeadStatus.DRAFT_READY, 0)
        reviewed_count = by_stage.get(LeadStatus.REVIEWED, 0)
        needs_revision_count = by_stage.get(LeadStatus.NEEDS_REVISION, 0)
        total_reviewed = draft_count + reviewed_count + needs_revision_count
        if total_reviewed > 0:
            rates["review_pass_rate"] = round(
                (reviewed_count / total_reviewed * 100), 2
            )

        # Contact rate (reviewed -> contacted)
        if reviewed_count > 0:
            contacted_count = by_stage.get(LeadStatus.CONTACTED, 0)
            rates["contact_rate"] = round((contacted_count / reviewed_count * 100), 2)

        # Reply rate (contacted -> replied)
        contacted_count = by_stage.get(LeadStatus.CONTACTED, 0)
        followed_up_count = by_stage.get(LeadStatus.FOLLOWED_UP, 0)
        total_contacted = contacted_count + followed_up_count
        if total_contacted > 0:
            replied_count = by_stage.get(LeadStatus.REPLIED, 0)
            rates["reply_rate"] = round((replied_count / total_contacted * 100), 2)

        # Meeting rate (replied -> meeting_booked)
        replied_count = by_stage.get(LeadStatus.REPLIED, 0)
        if replied_count > 0:
            meeting_count = by_stage.get(LeadStatus.MEETING_BOOKED, 0)
            rates["meeting_rate"] = round((meeting_count / replied_count * 100), 2)

        # Close rate (meeting_booked -> won)
        meeting_count = by_stage.get(LeadStatus.MEETING_BOOKED, 0)
        if meeting_count > 0:
            won_count = by_stage.get(LeadStatus.WON, 0)
            rates["close_rate"] = round((won_count / meeting_count * 100), 2)

        return rates

    def _empty_metrics(self) -> Dict[str, any]:
        """Return empty metrics structure.

        Returns:
            Empty metrics dictionary
        """
        return {
            "total": 0,
            "by_stage": {stage.value: 0 for stage in self.FUNNEL_STAGES},
            "conversion_rates": {},
            "win_rate": 0.0,
            "loss_rate": 0.0,
            "active_pipeline": 0,
        }

    def get_bottlenecks(self, leads: List[Lead]) -> List[Dict[str, any]]:
        """Identify funnel bottlenecks.

        Args:
            leads: List of leads

        Returns:
            List of bottleneck stages with counts and percentages
        """
        metrics = self.calculate_metrics(leads)
        by_stage = metrics["by_stage"]
        total = metrics["total"]

        if total == 0:
            return []

        bottlenecks = []

        # Stages with >20% of total pipeline are bottlenecks
        for stage_value, count in by_stage.items():
            if count > 0:
                percentage = count / total * 100
                if percentage > 20:
                    bottlenecks.append(
                        {
                            "stage": stage_value,
                            "count": count,
                            "percentage": round(percentage, 2),
                        }
                    )

        # Sort by percentage descending
        bottlenecks.sort(key=lambda x: x["percentage"], reverse=True)

        return bottlenecks

    def get_health_score(self, leads: List[Lead]) -> Dict[str, any]:
        """Calculate overall pipeline health score.

        Args:
            leads: List of leads

        Returns:
            Dictionary with health score (0-100) and status
        """
        metrics = self.calculate_metrics(leads)

        if metrics["total"] == 0:
            return {"score": 0, "status": "empty", "issues": ["No leads in pipeline"]}

        score = 100
        issues = []

        # Deduct points for low conversion rates
        rates = metrics["conversion_rates"]
        if rates.get("reply_rate", 0) < 10:
            score -= 20
            issues.append("Low reply rate (<10%)")
        if rates.get("meeting_rate", 0) < 20:
            score -= 15
            issues.append("Low meeting conversion (<20%)")
        if rates.get("close_rate", 0) < 30:
            score -= 15
            issues.append("Low close rate (<30%)")

        # Deduct points for high loss rate
        if metrics["loss_rate"] > 30:
            score -= 20
            issues.append(f"High loss rate ({metrics['loss_rate']}%)")

        # Deduct points for bottlenecks
        bottlenecks = self.get_bottlenecks(leads)
        if len(bottlenecks) > 2:
            score -= 10
            issues.append(f"Multiple bottlenecks detected ({len(bottlenecks)})")

        # Deduct points for small active pipeline
        if metrics["active_pipeline"] < 10:
            score -= 10
            issues.append("Small active pipeline (<10 leads)")

        # Determine status
        if score >= 80:
            status = "healthy"
        elif score >= 60:
            status = "fair"
        elif score >= 40:
            status = "poor"
        else:
            status = "critical"

        return {
            "score": max(0, score),
            "status": status,
            "issues": issues,
        }
