"""
Conversation Guard — Prevent infinite loops and agent-to-agent chatting.

Implements safeguards to:
1. Detect when two agents are chatting with each other (self-loop)
2. Detect conversation loops (A→B→A→B pattern)
3. Detect rapid-fire message exchanges (rate limiting)
4. Provide emergency stop mechanism
5. Log all suspicious activity for debugging
"""

import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration
MAX_MESSAGES_PER_CONVERSATION = 50  # Hard limit per conversation
MAX_MESSAGES_PER_MINUTE = 10  # Rate limit per conversation
MAX_CONSECUTIVE_AGENT_MESSAGES = 3  # Max agent messages in a row
LOOP_DETECTION_WINDOW = 10  # Check last N messages for loops
EMERGENCY_STOP_FILE = Path(__file__).parent.parent / ".sisyphus" / "emergency_stop"

# State tracking
_conversation_message_counts = defaultdict(int)
_conversation_timestamps = defaultdict(list)
_conversation_last_sender = defaultdict(str)
_conversation_consecutive_agent_msgs = defaultdict(int)
_loop_detection_cache = {}


def enable_emergency_stop() -> None:
    """Create emergency stop file to halt all conversation processing."""
    EMERGENCY_STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    EMERGENCY_STOP_FILE.write_text(
        json.dumps(
            {
                "enabled": True,
                "timestamp": time.time(),
                "reason": "Emergency stop activated",
            }
        )
    )
    logger.critical("🛑 EMERGENCY STOP ACTIVATED - All conversations halted")


def disable_emergency_stop() -> None:
    """Remove emergency stop file to resume conversation processing."""
    if EMERGENCY_STOP_FILE.exists():
        EMERGENCY_STOP_FILE.unlink()
    logger.info("✓ Emergency stop disabled - Conversations resumed")


def is_emergency_stop_active() -> bool:
    """Check if emergency stop is active."""
    return EMERGENCY_STOP_FILE.exists()


def check_emergency_stop(conversation_id: int) -> tuple[bool, str]:
    """
    Check if emergency stop is active.

    Returns:
        (should_skip, reason)
    """
    if is_emergency_stop_active():
        return True, "Emergency stop is active"
    return False, ""


def detect_self_loop(
    conversation_id: int,
    contact_phone: str,
    wa_number_id: str,
    session_name: str,
) -> tuple[bool, str]:
    """
    Detect if contact is the bot itself (self-loop).

    Args:
        conversation_id: Conversation ID
        contact_phone: Contact phone number
        wa_number_id: WhatsApp number ID
        session_name: WAHA session name

    Returns:
        (is_self_loop, reason)
    """
    from state_manager import get_wa_number_by_session

    try:
        wa_num_rec = get_wa_number_by_session(session_name)
        if wa_num_rec:
            own_phone = "".join(filter(str.isdigit, str(wa_num_rec.get("phone") or "")))
            clean_contact = "".join(filter(str.isdigit, str(contact_phone)))

            if own_phone and clean_contact == own_phone:
                logger.warning(
                    f"🔄 SELF-LOOP DETECTED: Conversation {conversation_id} - "
                    f"Contact {contact_phone} is the bot itself"
                )
                return True, "Contact is the bot itself (self-loop)"
    except Exception as e:
        logger.error(f"Error checking self-loop: {e}")

    return False, ""


def detect_conversation_loop(
    conversation_id: int,
    message_direction: str,  # "in" or "out"
    message_text: str,
) -> tuple[bool, str]:
    """
    Detect conversation loops (A→B→A→B pattern).

    Checks if the last N messages show a repeating pattern of
    incoming/outgoing messages with similar content.

    Args:
        conversation_id: Conversation ID
        message_direction: "in" (customer) or "out" (agent)
        message_text: Message content

    Returns:
        (is_loop, reason)
    """
    try:
        from conversation_tracker import get_conversation_context

        context = get_conversation_context(
            conversation_id, max_messages=LOOP_DETECTION_WINDOW
        )
        if not context or len(context) < 4:
            return False, ""

        # Check for alternating pattern (in→out→in→out)
        directions = [msg.get("direction") for msg in context[-LOOP_DETECTION_WINDOW:]]

        # Count alternations
        alternations = 0
        for i in range(1, len(directions)):
            if directions[i] != directions[i - 1]:
                alternations += 1

        # If more than 70% of messages alternate, it's likely a loop
        if len(directions) >= 4 and alternations / len(directions) > 0.7:
            logger.warning(
                f"🔄 CONVERSATION LOOP DETECTED: Conversation {conversation_id} - "
                f"Alternating pattern detected ({alternations}/{len(directions)} alternations)"
            )
            return True, "Conversation loop detected (alternating in/out pattern)"

    except Exception as e:
        logger.error(f"Error detecting conversation loop: {e}")

    return False, ""


def check_rate_limit(
    conversation_id: int,
    max_per_minute: int = MAX_MESSAGES_PER_MINUTE,
) -> tuple[bool, str]:
    """
    Check if conversation exceeds rate limit.

    Args:
        conversation_id: Conversation ID
        max_per_minute: Max messages per minute

    Returns:
        (is_rate_limited, reason)
    """
    now = time.time()
    timestamps = _conversation_timestamps[conversation_id]

    # Remove timestamps older than 1 minute
    timestamps[:] = [ts for ts in timestamps if now - ts < 60]

    if len(timestamps) >= max_per_minute:
        logger.warning(
            f"⚠️  RATE LIMIT EXCEEDED: Conversation {conversation_id} - "
            f"{len(timestamps)} messages in last 60 seconds"
        )
        return (
            True,
            f"Rate limit exceeded ({len(timestamps)}/{max_per_minute} per minute)",
        )

    timestamps.append(now)
    return False, ""


def check_message_count(
    conversation_id: int,
    max_messages: int = MAX_MESSAGES_PER_CONVERSATION,
) -> tuple[bool, str]:
    """
    Check if conversation exceeds maximum message count.

    Args:
        conversation_id: Conversation ID
        max_messages: Maximum messages allowed

    Returns:
        (is_exceeded, reason)
    """
    count = _conversation_message_counts[conversation_id]

    if count >= max_messages:
        logger.error(
            f"🛑 MESSAGE LIMIT EXCEEDED: Conversation {conversation_id} - "
            f"{count} messages (max: {max_messages})"
        )
        return (
            True,
            f"Conversation exceeded maximum message count ({count}/{max_messages})",
        )

    _conversation_message_counts[conversation_id] += 1
    return False, ""


def check_consecutive_agent_messages(
    conversation_id: int,
    message_direction: str,  # "in" or "out"
    max_consecutive: int = MAX_CONSECUTIVE_AGENT_MESSAGES,
) -> tuple[bool, str]:
    """
    Check if agent is sending too many consecutive messages without customer input.

    Args:
        conversation_id: Conversation ID
        message_direction: "in" (customer) or "out" (agent)
        max_consecutive: Max consecutive agent messages

    Returns:
        (is_exceeded, reason)
    """
    if message_direction == "in":
        # Customer message resets counter
        _conversation_consecutive_agent_msgs[conversation_id] = 0
        return False, ""

    # Agent message increments counter
    _conversation_consecutive_agent_msgs[conversation_id] += 1
    count = _conversation_consecutive_agent_msgs[conversation_id]

    if count > max_consecutive:
        logger.warning(
            f"⚠️  CONSECUTIVE AGENT MESSAGES: Conversation {conversation_id} - "
            f"{count} agent messages without customer input"
        )
        return True, f"Too many consecutive agent messages ({count}/{max_consecutive})"

    return False, ""


def run_all_checks(
    conversation_id: int,
    contact_phone: str,
    wa_number_id: str,
    session_name: str,
    message_direction: str,
    message_text: str,
) -> tuple[bool, str]:
    """
    Run all conversation guards.

    Returns:
        (should_skip, reason)
    """
    # 1. Emergency stop
    should_skip, reason = check_emergency_stop(conversation_id)
    if should_skip:
        return True, reason

    # 2. Self-loop detection
    is_loop, reason = detect_self_loop(
        conversation_id, contact_phone, wa_number_id, session_name
    )
    if is_loop:
        return True, reason

    # 3. Conversation loop detection
    is_loop, reason = detect_conversation_loop(
        conversation_id, message_direction, message_text
    )
    if is_loop:
        enable_emergency_stop()
        return True, reason

    # 4. Rate limit
    is_limited, reason = check_rate_limit(conversation_id)
    if is_limited:
        return True, reason

    # 5. Message count
    is_exceeded, reason = check_message_count(conversation_id)
    if is_exceeded:
        enable_emergency_stop()
        return True, reason

    # 6. Consecutive agent messages
    is_exceeded, reason = check_consecutive_agent_messages(
        conversation_id, message_direction
    )
    if is_exceeded:
        return True, reason

    return False, ""


def reset_conversation_state(conversation_id: int) -> None:
    """Reset tracking state for a conversation."""
    _conversation_message_counts[conversation_id] = 0
    _conversation_timestamps[conversation_id] = []
    _conversation_last_sender[conversation_id] = ""
    _conversation_consecutive_agent_msgs[conversation_id] = 0
    logger.info(f"✓ Reset conversation state for {conversation_id}")


def get_conversation_stats(conversation_id: int) -> dict:
    """Get current stats for a conversation."""
    return {
        "conversation_id": conversation_id,
        "message_count": _conversation_message_counts[conversation_id],
        "messages_last_minute": len(_conversation_timestamps[conversation_id]),
        "consecutive_agent_messages": _conversation_consecutive_agent_msgs[
            conversation_id
        ],
        "emergency_stop_active": is_emergency_stop_active(),
    }
