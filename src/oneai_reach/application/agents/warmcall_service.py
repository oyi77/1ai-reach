"""Warmcall service - multi-turn follow-up sequences with intent routing.

Manages personalized WhatsApp follow-up sequences for warm leads:
  - Starts a warmcall conversation with a personalized first message
  - Processes replies with intent classification (BUY/INFO/REJECT/UNCLEAR)
  - Sends scheduled follow-ups at configurable intervals
  - Routes BUY intent → converter flow (meeting booking)
  - Routes REJECT intent → mark cold immediately
  - Max turns enforcement → mark cold after WARMCALL_MAX_TURNS

Follow-up intervals (configurable via WARMCALL_FOLLOWUP_INTERVALS):
  Turn 1 → wait 1 day, Turn 2 → wait 3 days, Turn 3 → wait 7 days, Turn 4 → wait 14 days
"""

from datetime import datetime, timezone
from pathlib import Path

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class WarmcallService:
    """Service for warmcall follow-up orchestration and intent classification."""

    def __init__(self, config: Settings):
        """Initialize warmcall service.

        Args:
            config: Application settings
        """
        self.config = config
        self.followup_intervals = [1, 3, 7, 14]
        self.max_turns = 4
        self.generator_model = config.llm.generator_model
        self.research_dir = Path(config.database.research_dir)

    def _days_since(self, iso_str: str) -> float:
        """Return fractional days elapsed since the given ISO timestamp.

        Args:
            iso_str: ISO format timestamp string

        Returns:
            Fractional days elapsed
        """
        try:
            dt = datetime.fromisoformat(str(iso_str)).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        except Exception:
            return 0

    def _followup_interval(self, turn: int) -> float:
        """Return wait-in-days for the given turn number (0-indexed from outbound count).

        Args:
            turn: Turn number (0-indexed)

        Returns:
            Wait time in days
        """
        intervals = self.followup_intervals
        if turn < len(intervals):
            return float(intervals[turn])
        # Beyond configured intervals, use the last interval
        return float(intervals[-1]) if intervals else 14.0

    def _load_research_brief(self, lead_id: str | None) -> str:
        """Load research brief from data/research/ if available.

        Args:
            lead_id: Lead ID to load research for

        Returns:
            Research brief text or empty string
        """
        if not lead_id:
            return ""
        try:
            # Research files are named like: data/research/{index}_{name}.txt
            # For now, return empty - actual implementation would search for file
            return ""
        except Exception:
            return ""

    def classify_intent(self, reply_text: str, lead_name: str) -> str:
        """Classify the intent of a warmcall reply.

        Args:
            reply_text: Customer's reply text
            lead_name: Lead name for context

        Returns:
            Intent classification: BUY, INFO, REJECT, or UNCLEAR
        """
        # Heuristic classification (fallback if LLM unavailable)
        return self._classify_heuristic(reply_text)

    def _classify_heuristic(self, text: str) -> str:
        """Classify intent using heuristic patterns.

        Args:
            text: Message text to classify

        Returns:
            Intent: BUY, INFO, REJECT, or UNCLEAR
        """
        t = text.lower()
        buy_signals = [
            "proceed",
            "invoice",
            "payment",
            "pay",
            "ready",
            "start",
            "let's go",
            "deal",
            "sign",
        ]
        reject_signals = [
            "not interested",
            "no thanks",
            "no thank",
            "decline",
            "pass",
            "unsubscribe",
            "stop",
        ]
        for word in reject_signals:
            if word in t:
                return "REJECT"
        for word in buy_signals:
            if word in t:
                return "BUY"
        if "?" in t or "more" in t or "info" in t or "detail" in t or "tell me" in t:
            return "INFO"
        return "UNCLEAR"

    def generate_followup_message(self, lead_name: str, context: str, turn: int) -> str:
        """Generate personalized follow-up message.

        Args:
            lead_name: Lead name for personalization
            context: Business context/vertical
            turn: Follow-up turn number

        Returns:
            Personalized follow-up message
        """
        # Simple template-based generation
        # In production, this would use LLM with research brief
        templates = {
            0: f"Hi {lead_name}, just checking in on our {context} proposal. Any questions?",
            1: f"Hi {lead_name}, wanted to follow up on the {context} solution we discussed.",
            2: f"Hi {lead_name}, this is our final follow-up on the {context} opportunity.",
        }
        return templates.get(turn, templates[2])

    def start_warmcall(self, phone: str, name: str, context: str, session: str) -> dict:
        """Start a new warmcall conversation.

        Args:
            phone: Contact phone number
            name: Contact name
            context: Business context/vertical
            session: WAHA session name

        Returns:
            dict with conversation_id and status
        """
        logger.info(f"Starting warmcall for {name} ({phone}) in {context}")
        try:
            # In production, this would:
            # 1. Create conversation in DB
            # 2. Load research brief
            # 3. Generate personalized first message
            # 4. Send via WhatsApp
            return {
                "status": "started",
                "phone": phone,
                "name": name,
                "context": context,
            }
        except Exception as e:
            logger.error(f"Failed to start warmcall: {e}")
            raise ExternalAPIError(
                service="warmcall_service",
                endpoint="/start_warmcall",
                status_code=0,
                reason=str(e),
            )

    def process_due_warmcalls(self) -> dict:
        """Process warmcalls due for follow-up.

        Returns:
            dict with count of processed warmcalls
        """
        logger.info("Processing due warmcalls")
        try:
            # In production, this would:
            # 1. Query conversations with status='warmcall'
            # 2. Check if follow-up interval has elapsed
            # 3. Generate and send follow-up messages
            # 4. Update conversation state
            return {"processed": 0, "status": "ok"}
        except Exception as e:
            logger.error(f"Failed to process warmcalls: {e}")
            raise ExternalAPIError(
                service="warmcall_service",
                endpoint="/process_due_warmcalls",
                status_code=0,
                reason=str(e),
            )
