import pytest
from datetime import datetime, timedelta

from oneai_reach.domain.models.lead import Lead, LeadStatus
from oneai_reach.domain.models.proposal import Proposal
from oneai_reach.domain.services.lead_scoring_service import LeadScoringService
from oneai_reach.domain.services.proposal_validator import ProposalValidator
from oneai_reach.domain.services.funnel_calculator import FunnelCalculator
from oneai_reach.domain.services.conversation_analyzer import ConversationAnalyzer


class TestLeadScoringService:
    @pytest.fixture
    def service(self):
        return LeadScoringService()

    def test_base_score_only(self, service):
        lead = Lead(id="1", displayName="Test")
        assert service.calculate_score(lead) == 20

    def test_score_with_email(self, service):
        lead = Lead(id="1", displayName="Test", email="test@example.com")
        assert service.calculate_score(lead) == 35

    def test_score_with_phone(self, service):
        lead = Lead(id="1", displayName="Test", phone="+628123456789")
        assert service.calculate_score(lead) == 35

    def test_score_with_email_and_phone(self, service):
        lead = Lead(
            id="1", displayName="Test", email="test@example.com", phone="+628123456789"
        )
        assert service.calculate_score(lead) == 50

    def test_score_with_website(self, service):
        lead = Lead(id="1", displayName="Test", websiteUri="https://example.com")
        assert service.calculate_score(lead) == 30

    def test_score_with_linkedin(self, service):
        lead = Lead(id="1", displayName="Test", linkedin="https://linkedin.com/in/test")
        assert service.calculate_score(lead) == 30

    def test_score_with_research(self, service):
        lead = Lead(id="1", displayName="Test", research="Research notes")
        assert service.calculate_score(lead) == 30

    def test_score_with_replied_status(self, service):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.REPLIED)
        assert service.calculate_score(lead) == 40

    def test_score_with_meeting_booked_status(self, service):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.MEETING_BOOKED)
        assert service.calculate_score(lead) == 50

    def test_score_with_won_status(self, service):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.WON)
        assert service.calculate_score(lead) == 50

    def test_score_with_cold_status(self, service):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.COLD)
        assert service.calculate_score(lead) == 0

    def test_score_with_lost_status(self, service):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.LOST)
        assert service.calculate_score(lead) == 0

    def test_score_with_unsubscribed_status(self, service):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.UNSUBSCRIBED)
        assert service.calculate_score(lead) == 0

    def test_score_maximum(self, service):
        lead = Lead(
            id="1",
            displayName="Test",
            email="test@example.com",
            phone="+628123456789",
            websiteUri="https://example.com",
            linkedin="https://linkedin.com/in/test",
            research="Research notes",
            status=LeadStatus.WON,
        )
        assert service.calculate_score(lead) == 100

    def test_score_clamped_to_zero(self, service):
        lead = Lead(
            id="1",
            displayName="Test",
            status=LeadStatus.COLD,
        )
        score = service.calculate_score(lead)
        assert score == 0

    def test_get_score_category_hot(self, service):
        assert service.get_score_category(70) == "hot"
        assert service.get_score_category(100) == "hot"

    def test_get_score_category_warm(self, service):
        assert service.get_score_category(50) == "warm"
        assert service.get_score_category(69) == "warm"

    def test_get_score_category_cold(self, service):
        assert service.get_score_category(30) == "cold"
        assert service.get_score_category(49) == "cold"

    def test_get_score_category_dead(self, service):
        assert service.get_score_category(0) == "dead"
        assert service.get_score_category(29) == "dead"

    def test_is_ready_for_outreach_true(self, service):
        lead = Lead(
            id="1", displayName="Test", email="test@example.com", phone="+628123456789"
        )
        assert service.is_ready_for_outreach(lead) is True

    def test_is_ready_for_outreach_false(self, service):
        lead = Lead(id="1", displayName="Test", email="test@example.com")
        assert service.is_ready_for_outreach(lead) is False


class TestProposalValidator:
    @pytest.fixture
    def validator(self):
        return ProposalValidator()

    def test_is_passing_true(self, validator):
        assert validator.is_passing(6) is True
        assert validator.is_passing(7) is True
        assert validator.is_passing(10) is True

    def test_is_passing_false(self, validator):
        assert validator.is_passing(5) is False
        assert validator.is_passing(0) is False

    def test_is_high_quality_true(self, validator):
        assert validator.is_high_quality(7) is True
        assert validator.is_high_quality(10) is True

    def test_is_high_quality_false(self, validator):
        assert validator.is_high_quality(6) is False
        assert validator.is_high_quality(5) is False

    def test_custom_threshold(self):
        validator = ProposalValidator(pass_threshold=7)
        assert validator.is_passing(7) is True
        assert validator.is_passing(6) is False

    def test_validate_proposal_valid(self, validator):
        content = " ".join(["word"] * 100)
        proposal = Proposal(lead_id="1", content=content, score=8.0)
        result = validator.validate_proposal(proposal)
        assert result["valid"] is True
        assert result["passing"] is True
        assert result["high_quality"] is True
        assert result["issues"] == []

    def test_validate_proposal_no_score(self, validator):
        content = " ".join(["word"] * 100)
        proposal = Proposal(lead_id="1", content=content, score=None)
        result = validator.validate_proposal(proposal)
        assert result["valid"] is False
        assert result["passing"] is False
        assert "Proposal has not been scored" in result["issues"]

    def test_validate_proposal_low_score(self, validator):
        content = " ".join(["word"] * 100)
        proposal = Proposal(lead_id="1", content=content, score=4.0)
        result = validator.validate_proposal(proposal)
        assert result["valid"] is False
        assert result["passing"] is False
        assert any("Score too low" in issue for issue in result["issues"])

    def test_validate_proposal_too_short(self, validator):
        proposal = Proposal(lead_id="1", content="Short", score=8.0)
        result = validator.validate_proposal(proposal)
        assert result["valid"] is False
        assert any("Content too short" in issue for issue in result["issues"])

    def test_validate_proposal_too_long(self, validator):
        content = " ".join(["word"] * 600)
        proposal = Proposal(lead_id="1", content=content, score=8.0)
        result = validator.validate_proposal(proposal)
        assert result["valid"] is False
        assert any("Content too long" in issue for issue in result["issues"])

    def test_validate_proposal_empty_content(self, validator):
        proposal = Proposal(lead_id="1", content="   ", score=8.0)
        result = validator.validate_proposal(proposal)
        assert result["valid"] is False
        assert "Content is empty" in result["issues"]

    def test_needs_revision_true(self, validator):
        proposal = Proposal(lead_id="1", content="Short", score=5.0)
        assert validator.needs_revision(proposal) is True

    def test_needs_revision_false(self, validator):
        content = " ".join(["word"] * 100)
        proposal = Proposal(lead_id="1", content=content, score=8.0)
        assert validator.needs_revision(proposal) is False

    def test_get_revision_priority_critical_no_score(self, validator):
        content = " ".join(["word"] * 100)
        proposal = Proposal(lead_id="1", content=content, score=None)
        assert validator.get_revision_priority(proposal) == "critical"

    def test_get_revision_priority_critical_empty(self, validator):
        proposal = Proposal(lead_id="1", content="", score=8.0)
        assert validator.get_revision_priority(proposal) == "critical"

    def test_get_revision_priority_high(self, validator):
        content = " ".join(["word"] * 100)
        proposal = Proposal(lead_id="1", content=content, score=3.0)
        assert validator.get_revision_priority(proposal) == "high"

    def test_get_revision_priority_medium(self, validator):
        content = " ".join(["word"] * 100)
        proposal = Proposal(lead_id="1", content=content, score=5.0)
        assert validator.get_revision_priority(proposal) == "medium"

    def test_get_revision_priority_low(self, validator):
        proposal = Proposal(lead_id="1", content="Short", score=7.0)
        assert validator.get_revision_priority(proposal) == "low"

    def test_get_revision_priority_none(self, validator):
        content = " ".join(["word"] * 100)
        proposal = Proposal(lead_id="1", content=content, score=8.0)
        assert validator.get_revision_priority(proposal) == "none"

    def test_format_validation_report(self, validator):
        content = " ".join(["word"] * 100)
        proposal = Proposal(lead_id="1", content=content, score=8.0)
        report = validator.format_validation_report(proposal)
        assert "Proposal Validation Report" in report
        assert "Lead ID: 1" in report
        assert "Score: 8.0/10" in report
        assert "✅ PASS" in report


class TestFunnelCalculator:
    @pytest.fixture
    def calculator(self):
        return FunnelCalculator()

    def test_calculate_metrics_empty(self, calculator):
        metrics = calculator.calculate_metrics([])
        assert metrics["total"] == 0
        assert metrics["active_pipeline"] == 0
        assert metrics["win_rate"] == 0.0
        assert metrics["loss_rate"] == 0.0

    def test_calculate_metrics_single_lead(self, calculator):
        leads = [Lead(id="1", displayName="Test", status=LeadStatus.NEW)]
        metrics = calculator.calculate_metrics(leads)
        assert metrics["total"] == 1
        assert metrics["by_stage"]["new"] == 1
        assert metrics["active_pipeline"] == 1

    def test_calculate_metrics_multiple_leads(self, calculator):
        leads = [
            Lead(id="1", displayName="Test1", status=LeadStatus.NEW),
            Lead(id="2", displayName="Test2", status=LeadStatus.CONTACTED),
            Lead(id="3", displayName="Test3", status=LeadStatus.WON),
        ]
        metrics = calculator.calculate_metrics(leads)
        assert metrics["total"] == 3
        assert metrics["by_stage"]["new"] == 1
        assert metrics["by_stage"]["contacted"] == 1
        assert metrics["by_stage"]["won"] == 1

    def test_calculate_metrics_win_rate(self, calculator):
        leads = [
            Lead(id="1", displayName="Test1", status=LeadStatus.WON),
            Lead(id="2", displayName="Test2", status=LeadStatus.LOST),
            Lead(id="3", displayName="Test3", status=LeadStatus.NEW),
        ]
        metrics = calculator.calculate_metrics(leads)
        assert metrics["win_rate"] == 33.33

    def test_calculate_metrics_loss_rate(self, calculator):
        leads = [
            Lead(id="1", displayName="Test1", status=LeadStatus.LOST),
            Lead(id="2", displayName="Test2", status=LeadStatus.COLD),
            Lead(id="3", displayName="Test3", status=LeadStatus.NEW),
            Lead(id="4", displayName="Test4", status=LeadStatus.NEW),
        ]
        metrics = calculator.calculate_metrics(leads)
        assert metrics["loss_rate"] == 50.0

    def test_calculate_metrics_active_pipeline(self, calculator):
        leads = [
            Lead(id="1", displayName="Test1", status=LeadStatus.NEW),
            Lead(id="2", displayName="Test2", status=LeadStatus.CONTACTED),
            Lead(id="3", displayName="Test3", status=LeadStatus.WON),
            Lead(id="4", displayName="Test4", status=LeadStatus.LOST),
        ]
        metrics = calculator.calculate_metrics(leads)
        assert metrics["active_pipeline"] == 2

    def test_calculate_conversion_rates_enrichment(self, calculator):
        leads = [
            Lead(id="1", displayName="Test1", status=LeadStatus.NEW),
            Lead(id="2", displayName="Test2", status=LeadStatus.ENRICHED),
            Lead(id="3", displayName="Test3", status=LeadStatus.ENRICHED),
        ]
        metrics = calculator.calculate_metrics(leads)
        assert metrics["conversion_rates"]["enrichment_rate"] == 66.67

    def test_calculate_conversion_rates_reply(self, calculator):
        leads = [
            Lead(id="1", displayName="Test1", status=LeadStatus.CONTACTED),
            Lead(id="2", displayName="Test2", status=LeadStatus.CONTACTED),
            Lead(id="3", displayName="Test3", status=LeadStatus.REPLIED),
        ]
        metrics = calculator.calculate_metrics(leads)
        assert metrics["conversion_rates"]["reply_rate"] == 50.0

    def test_get_bottlenecks_empty(self, calculator):
        bottlenecks = calculator.get_bottlenecks([])
        assert bottlenecks == []

    def test_get_bottlenecks_detected(self, calculator):
        leads = [
            Lead(id=str(i), displayName=f"Test{i}", status=LeadStatus.NEW)
            for i in range(10)
        ]
        bottlenecks = calculator.get_bottlenecks(leads)
        assert len(bottlenecks) > 0
        assert bottlenecks[0]["stage"] == "new"
        assert bottlenecks[0]["percentage"] == 100.0

    def test_get_health_score_empty(self, calculator):
        health = calculator.get_health_score([])
        assert health["score"] == 0
        assert health["status"] == "empty"

    def test_get_health_score_healthy(self, calculator):
        leads = [
            Lead(id=str(i), displayName=f"Test{i}", status=LeadStatus.CONTACTED)
            for i in range(20)
        ]
        health = calculator.get_health_score(leads)
        assert health["score"] >= 50

    def test_get_health_score_low_reply_rate(self, calculator):
        leads = [
            Lead(id=str(i), displayName=f"Test{i}", status=LeadStatus.CONTACTED)
            for i in range(20)
        ]
        health = calculator.get_health_score(leads)
        assert any("Low reply rate" in issue for issue in health["issues"])

    def test_get_health_score_high_loss_rate(self, calculator):
        leads = [
            Lead(id="1", displayName="Test1", status=LeadStatus.LOST),
            Lead(id="2", displayName="Test2", status=LeadStatus.LOST),
            Lead(id="3", displayName="Test3", status=LeadStatus.NEW),
        ]
        health = calculator.get_health_score(leads)
        assert any("High loss rate" in issue for issue in health["issues"])

    def test_get_health_score_small_pipeline(self, calculator):
        leads = [
            Lead(id="1", displayName="Test1", status=LeadStatus.NEW),
            Lead(id="2", displayName="Test2", status=LeadStatus.WON),
        ]
        health = calculator.get_health_score(leads)
        assert any("Small active pipeline" in issue for issue in health["issues"])


class TestConversationAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return ConversationAnalyzer()

    def test_analyze_positive_sentiment(self, analyzer):
        result = analyzer.analyze("Terima kasih, produknya bagus!")
        assert result["sentiment"] == "positive"

    def test_analyze_negative_sentiment(self, analyzer):
        result = analyzer.analyze("Produknya jelek dan mahal")
        assert result["sentiment"] == "negative"

    def test_analyze_neutral_sentiment(self, analyzer):
        result = analyzer.analyze("Saya ingin tahu lebih lanjut")
        assert result["sentiment"] == "neutral"

    def test_analyze_question_intent(self, analyzer):
        result = analyzer.analyze("Kapan produk ini tersedia?")
        assert result["intent"] == "question"

    def test_analyze_complaint_intent(self, analyzer):
        result = analyzer.analyze("Saya komplain, produk rusak")
        assert result["intent"] == "complaint"

    def test_analyze_purchase_intent(self, analyzer):
        result = analyzer.analyze("Saya mau beli produk ini")
        assert result["intent"] == "purchase"

    def test_analyze_feedback_intent(self, analyzer):
        result = analyzer.analyze("Saya ingin memberikan saran")
        assert result["intent"] == "feedback"

    def test_analyze_other_intent(self, analyzer):
        result = analyzer.analyze("Hello")
        assert result["intent"] == "other"

    def test_analyze_high_engagement(self, analyzer):
        long_text = " ".join(["word"] * 40)
        result = analyzer.analyze(long_text)
        assert result["engagement"] == "high"

    def test_analyze_low_engagement(self, analyzer):
        result = analyzer.analyze("Ya")
        assert result["engagement"] == "low"

    def test_analyze_medium_engagement(self, analyzer):
        result = analyzer.analyze("Saya ingin tahu lebih lanjut tentang produk")
        assert result["engagement"] == "medium"

    def test_analyze_confidence(self, analyzer):
        result = analyzer.analyze("Short text")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_batch_analyze(self, analyzer):
        texts = ["Terima kasih", "Kapan tersedia?", "Produk jelek"]
        results = analyzer.batch_analyze(texts)
        assert len(results) == 3
        assert results[0]["sentiment"] == "positive"
        assert results[1]["intent"] == "question"
        assert results[2]["sentiment"] == "negative"

    def test_get_aggregate_sentiment_empty(self, analyzer):
        result = analyzer.get_aggregate_sentiment([])
        assert result["overall"] == "neutral"
        assert result["total"] == 0

    def test_get_aggregate_sentiment_positive(self, analyzer):
        texts = ["Terima kasih", "Bagus sekali", "Saya suka"]
        result = analyzer.get_aggregate_sentiment(texts)
        assert result["overall"] == "positive"
        assert result["positive_count"] == 3
        assert result["total"] == 3

    def test_get_aggregate_sentiment_negative(self, analyzer):
        texts = ["Jelek", "Buruk", "Kecewa"]
        result = analyzer.get_aggregate_sentiment(texts)
        assert result["overall"] == "negative"
        assert result["negative_count"] == 3

    def test_get_aggregate_sentiment_mixed(self, analyzer):
        texts = ["Terima kasih", "Jelek", "Halo"]
        result = analyzer.get_aggregate_sentiment(texts)
        assert result["total"] == 3
        assert result["positive_count"] == 1
        assert result["negative_count"] == 1
        assert result["neutral_count"] == 1
