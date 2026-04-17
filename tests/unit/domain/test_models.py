import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError

from oneai_reach.domain.models.lead import Lead, LeadStatus
from oneai_reach.domain.models.conversation import (
    Conversation,
    ConversationStatus,
    EngineMode,
)
from oneai_reach.domain.models.message import Message, MessageDirection, MessageType
from oneai_reach.domain.models.proposal import Proposal
from oneai_reach.domain.models.knowledge import KnowledgeEntry, KnowledgeCategory


class TestLeadModel:
    def test_email_validation_valid(self):
        lead = Lead(id="1", displayName="Test Lead", email="test@example.com")
        assert lead.email == "test@example.com"

    def test_email_validation_invalid(self):
        with pytest.raises(ValidationError):
            Lead(id="1", displayName="Test Lead", email="not-an-email")

    @pytest.mark.parametrize(
        "input_phone,expected",
        [
            ("081234567890", "+6281234567890"),
            ("+6281234567890", "+6281234567890"),
            ("6281234567890", "+6281234567890"),
        ],
    )
    def test_phone_normalization(self, input_phone, expected):
        lead = Lead(id="1", displayName="Test", phone=input_phone)
        assert lead.phone == expected

    def test_phone_empty_string(self):
        lead = Lead(id="1", displayName="Test", phone="   ")
        assert lead.phone is None

    def test_phone_none(self):
        lead = Lead(id="1", displayName="Test", phone=None)
        assert lead.phone is None

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("example.com", "https://example.com"),
            ("http://example.com", "http://example.com"),
            ("https://example.com", "https://example.com"),
            ("", None),
            ("   ", None),
        ],
    )
    def test_url_validation(self, input_url, expected):
        lead = Lead(id="1", displayName="Test", websiteUri=input_url)
        assert lead.websiteUri == expected

    def test_is_warm_replied(self):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.REPLIED)
        assert lead.is_warm is True

    def test_is_warm_meeting_booked(self):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.MEETING_BOOKED)
        assert lead.is_warm is True

    def test_is_warm_contacted(self):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.CONTACTED)
        assert lead.is_warm is False

    def test_is_cold_status(self):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.COLD)
        assert lead.is_cold is True

    def test_is_cold_lost(self):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.LOST)
        assert lead.is_cold is True

    def test_is_cold_unsubscribed(self):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.UNSUBSCRIBED)
        assert lead.is_cold is True

    def test_is_cold_new(self):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.NEW)
        assert lead.is_cold is False

    def test_days_since_contact_none(self):
        lead = Lead(id="1", displayName="Test")
        assert lead.days_since_contact is None

    def test_days_since_contact_calculated(self):
        past_date = datetime.now() - timedelta(days=5)
        lead = Lead(id="1", displayName="Test", contacted_at=past_date)
        assert lead.days_since_contact == 5

    def test_days_since_reply_none(self):
        lead = Lead(id="1", displayName="Test")
        assert lead.days_since_reply is None

    def test_days_since_reply_calculated(self):
        past_date = datetime.now() - timedelta(days=3)
        lead = Lead(id="1", displayName="Test", replied_at=past_date)
        assert lead.days_since_reply == 3

    def test_needs_followup_not_contacted(self):
        lead = Lead(id="1", displayName="Test", status=LeadStatus.NEW)
        assert lead.needs_followup is False

    def test_needs_followup_with_followup_date(self):
        past_date = datetime.now() - timedelta(days=1)
        lead = Lead(
            id="1",
            displayName="Test",
            status=LeadStatus.CONTACTED,
            followup_at=past_date,
        )
        assert lead.needs_followup is True

    def test_needs_followup_after_3_days(self):
        past_date = datetime.now() - timedelta(days=4)
        lead = Lead(
            id="1",
            displayName="Test",
            status=LeadStatus.CONTACTED,
            contacted_at=past_date,
        )
        assert lead.needs_followup is True

    def test_needs_followup_before_3_days(self):
        past_date = datetime.now() - timedelta(days=2)
        lead = Lead(
            id="1",
            displayName="Test",
            status=LeadStatus.CONTACTED,
            contacted_at=past_date,
        )
        assert lead.needs_followup is False

    def test_is_replied_true(self):
        lead = Lead(id="1", displayName="Test", replied_at=datetime.now())
        assert lead.is_replied is True

    def test_is_replied_false(self):
        lead = Lead(id="1", displayName="Test")
        assert lead.is_replied is False


class TestConversationModel:
    def test_is_active_true(self):
        conv = Conversation(
            wa_number_id="1",
            contact_phone="+628123456789",
            status=ConversationStatus.ACTIVE,
        )
        assert conv.is_active is True

    def test_is_active_false(self):
        conv = Conversation(
            wa_number_id="1",
            contact_phone="+628123456789",
            status=ConversationStatus.RESOLVED,
        )
        assert conv.is_active is False

    def test_is_escalated_true(self):
        conv = Conversation(
            wa_number_id="1",
            contact_phone="+628123456789",
            status=ConversationStatus.ESCALATED,
        )
        assert conv.is_escalated is True

    def test_is_escalated_false(self):
        conv = Conversation(
            wa_number_id="1",
            contact_phone="+628123456789",
            status=ConversationStatus.ACTIVE,
        )
        assert conv.is_escalated is False

    def test_hours_since_last_message_none(self):
        conv = Conversation(wa_number_id="1", contact_phone="+628123456789")
        assert conv.hours_since_last_message is None

    def test_hours_since_last_message_calculated(self):
        past_time = datetime.now() - timedelta(hours=5)
        conv = Conversation(
            wa_number_id="1", contact_phone="+628123456789", last_message_at=past_time
        )
        hours = conv.hours_since_last_message
        assert hours is not None
        assert 4.9 <= hours <= 5.1

    def test_is_stale_true(self):
        past_time = datetime.now() - timedelta(hours=50)
        conv = Conversation(
            wa_number_id="1", contact_phone="+628123456789", last_message_at=past_time
        )
        assert conv.is_stale is True

    def test_is_stale_false(self):
        past_time = datetime.now() - timedelta(hours=24)
        conv = Conversation(
            wa_number_id="1", contact_phone="+628123456789", last_message_at=past_time
        )
        assert conv.is_stale is False

    def test_is_stale_none(self):
        conv = Conversation(wa_number_id="1", contact_phone="+628123456789")
        assert conv.is_stale is False

    def test_is_cold_lead_true(self):
        conv = Conversation(
            wa_number_id="1", contact_phone="+628123456789", engine_mode=EngineMode.COLD
        )
        assert conv.is_cold_lead is True

    def test_is_cold_lead_false(self):
        conv = Conversation(
            wa_number_id="1", contact_phone="+628123456789", engine_mode=EngineMode.CS
        )
        assert conv.is_cold_lead is False


class TestMessageModel:
    def test_is_incoming_true(self):
        msg = Message(conversation_id=1, direction=MessageDirection.IN)
        assert msg.is_incoming is True

    def test_is_incoming_false(self):
        msg = Message(conversation_id=1, direction=MessageDirection.OUT)
        assert msg.is_incoming is False

    def test_is_outgoing_true(self):
        msg = Message(conversation_id=1, direction=MessageDirection.OUT)
        assert msg.is_outgoing is True

    def test_is_outgoing_false(self):
        msg = Message(conversation_id=1, direction=MessageDirection.IN)
        assert msg.is_outgoing is False

    def test_is_voice_true(self):
        msg = Message(
            conversation_id=1,
            direction=MessageDirection.IN,
            message_type=MessageType.VOICE,
        )
        assert msg.is_voice is True

    def test_is_voice_false(self):
        msg = Message(
            conversation_id=1,
            direction=MessageDirection.IN,
            message_type=MessageType.TEXT,
        )
        assert msg.is_voice is False

    @pytest.mark.parametrize(
        "msg_type",
        [
            MessageType.IMAGE,
            MessageType.VIDEO,
            MessageType.AUDIO,
            MessageType.DOCUMENT,
            MessageType.VOICE,
        ],
    )
    def test_is_media_true(self, msg_type):
        msg = Message(
            conversation_id=1, direction=MessageDirection.IN, message_type=msg_type
        )
        assert msg.is_media is True

    @pytest.mark.parametrize(
        "msg_type",
        [
            MessageType.TEXT,
            MessageType.STICKER,
            MessageType.LOCATION,
            MessageType.CONTACT,
        ],
    )
    def test_is_media_false(self, msg_type):
        msg = Message(
            conversation_id=1, direction=MessageDirection.IN, message_type=msg_type
        )
        assert msg.is_media is False

    def test_age_minutes_none(self):
        msg = Message(conversation_id=1, direction=MessageDirection.IN)
        assert msg.age_minutes is None

    def test_age_minutes_calculated(self):
        past_time = datetime.now() - timedelta(minutes=10)
        msg = Message(
            conversation_id=1, direction=MessageDirection.IN, timestamp=past_time
        )
        age = msg.age_minutes
        assert age is not None
        assert 9.9 <= age <= 10.1


class TestProposalModel:
    def test_score_validation_valid(self):
        proposal = Proposal(lead_id="1", content="Test content", score=7.5)
        assert proposal.score == 7.5

    def test_score_validation_rounded(self):
        proposal = Proposal(lead_id="1", content="Test content", score=7.555)
        assert proposal.score == 7.55

    def test_score_validation_min(self):
        proposal = Proposal(lead_id="1", content="Test content", score=0.0)
        assert proposal.score == 0.0

    def test_score_validation_max(self):
        proposal = Proposal(lead_id="1", content="Test content", score=10.0)
        assert proposal.score == 10.0

    def test_score_validation_below_min(self):
        with pytest.raises(ValidationError):
            Proposal(lead_id="1", content="Test content", score=-0.1)

    def test_score_validation_above_max(self):
        with pytest.raises(ValidationError):
            Proposal(lead_id="1", content="Test content", score=10.1)

    def test_score_none(self):
        proposal = Proposal(lead_id="1", content="Test content", score=None)
        assert proposal.score is None

    def test_is_high_quality_true(self):
        proposal = Proposal(lead_id="1", content="Test content", score=7.0)
        assert proposal.is_high_quality is True

    def test_is_high_quality_false(self):
        proposal = Proposal(lead_id="1", content="Test content", score=6.9)
        assert proposal.is_high_quality is False

    def test_is_high_quality_none(self):
        proposal = Proposal(lead_id="1", content="Test content", score=None)
        assert proposal.is_high_quality is False

    def test_is_reviewed_true(self):
        proposal = Proposal(
            lead_id="1",
            content="Test content",
            reviewed=True,
            reviewed_at=datetime.now(),
        )
        assert proposal.is_reviewed is True

    def test_is_reviewed_false_not_reviewed(self):
        proposal = Proposal(lead_id="1", content="Test content", reviewed=False)
        assert proposal.is_reviewed is False

    def test_is_reviewed_false_no_timestamp(self):
        proposal = Proposal(lead_id="1", content="Test content", reviewed=True)
        assert proposal.is_reviewed is False

    def test_needs_revision_true(self):
        proposal = Proposal(lead_id="1", content="Test content", score=4.9)
        assert proposal.needs_revision is True

    def test_needs_revision_false(self):
        proposal = Proposal(lead_id="1", content="Test content", score=5.0)
        assert proposal.needs_revision is False

    def test_needs_revision_none(self):
        proposal = Proposal(lead_id="1", content="Test content", score=None)
        assert proposal.needs_revision is False

    def test_word_count(self):
        proposal = Proposal(lead_id="1", content="This is a test proposal content")
        assert proposal.word_count == 6

    def test_char_count(self):
        proposal = Proposal(lead_id="1", content="Test")
        assert proposal.char_count == 4


class TestKnowledgeEntryModel:
    def test_priority_validation_valid(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            priority=5,
        )
        assert entry.priority == 5

    def test_priority_validation_min(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            priority=0,
        )
        assert entry.priority == 0

    def test_priority_validation_max(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            priority=10,
        )
        assert entry.priority == 10

    def test_priority_validation_below_min(self):
        with pytest.raises(ValidationError):
            KnowledgeEntry(
                wa_number_id="1",
                category=KnowledgeCategory.FAQ,
                question="Test?",
                answer="Answer",
                priority=-1,
            )

    def test_priority_validation_above_max(self):
        with pytest.raises(ValidationError):
            KnowledgeEntry(
                wa_number_id="1",
                category=KnowledgeCategory.FAQ,
                question="Test?",
                answer="Answer",
                priority=11,
            )

    def test_tags_normalization(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            tags="Python, Django, API",
        )
        assert entry.tags == "python,django,api"

    def test_tags_empty_string(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            tags="   ",
        )
        assert entry.tags is None

    def test_tags_none(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            tags=None,
        )
        assert entry.tags is None

    def test_is_faq_true(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
        )
        assert entry.is_faq is True

    def test_is_faq_false(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.DOC,
            question="Test?",
            answer="Answer",
        )
        assert entry.is_faq is False

    def test_is_snippet_true(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.SNIPPET,
            question="Test?",
            answer="Answer",
        )
        assert entry.is_snippet is True

    def test_is_snippet_false(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
        )
        assert entry.is_snippet is False

    def test_is_high_priority_true(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            priority=7,
        )
        assert entry.is_high_priority is True

    def test_is_high_priority_false(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            priority=6,
        )
        assert entry.is_high_priority is False

    def test_tag_list(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            tags="python,django,api",
        )
        assert entry.tag_list == ["python", "django", "api"]

    def test_tag_list_empty(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="Test?",
            answer="Answer",
            tags=None,
        )
        assert entry.tag_list == []

    def test_searchable_text(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="What is Python?",
            answer="A programming language",
            content="Python is great for web development",
        )
        assert "What is Python?" in entry.searchable_text
        assert "A programming language" in entry.searchable_text
        assert "Python is great for web development" in entry.searchable_text

    def test_searchable_text_no_content(self):
        entry = KnowledgeEntry(
            wa_number_id="1",
            category=KnowledgeCategory.FAQ,
            question="What is Python?",
            answer="A programming language",
        )
        assert entry.searchable_text == "What is Python? A programming language"
