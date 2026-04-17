"""Domain models package."""

from oneai_reach.domain.models.lead import Lead, LeadStatus
from oneai_reach.domain.models.conversation import (
    Conversation,
    ConversationStatus,
    EngineMode,
)
from oneai_reach.domain.models.message import Message, MessageDirection, MessageType
from oneai_reach.domain.models.proposal import Proposal
from oneai_reach.domain.models.knowledge import KnowledgeEntry, KnowledgeCategory

__all__ = [
    "Lead",
    "LeadStatus",
    "Conversation",
    "ConversationStatus",
    "EngineMode",
    "Message",
    "MessageDirection",
    "MessageType",
    "Proposal",
    "KnowledgeEntry",
    "KnowledgeCategory",
]
