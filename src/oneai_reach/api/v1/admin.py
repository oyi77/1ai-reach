"""Admin control endpoints for manual conversation management.

Provides emergency controls for stopping/pausing conversations and monitoring
active conversation state. Part of the infinite loop prevention system.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from oneai_reach.api.dependencies import verify_api_key

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(verify_api_key)],
)

# Global pause flag for CS engine
_PAUSE_CS_ENGINE = False


class ConversationInfo(BaseModel):
    """Active conversation information."""

    conversation_id: int
    wa_number_id: str
    contact_phone: str
    message_count: int
    last_message_time: Optional[str] = None
    status: str = "active"
    engine_mode: str = "cs"


class AdminResponse(BaseModel):
    """Standard admin endpoint response."""

    status: str
    message: str
    data: Optional[Dict[str, Any]] = None


def get_pause_flag() -> bool:
    """Get current pause flag state (for CS engine integration)."""
    return _PAUSE_CS_ENGINE


@router.get("/conversations", response_model=List[ConversationInfo])
async def list_conversations() -> List[ConversationInfo]:
    """List all active conversations with message counts.

    Returns conversation details including message counts and last activity
    for monitoring and debugging purposes.
    """
    try:
        import sys
        from pathlib import Path

        scripts_dir = (
            Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
        )
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        import conversation_tracker

        convs = conversation_tracker.get_active_conversations()

        result = []
        for conv in convs:
            # Skip conversations with missing wa_number_id (data integrity issue)
            wa_number_id = conv.get("wa_number_id")
            if wa_number_id is None:
                wa_number_id = "unknown"

            result.append(
                ConversationInfo(
                    conversation_id=conv.get("id", 0),
                    wa_number_id=wa_number_id,
                    contact_phone=conv.get("contact_phone", ""),
                    message_count=conv.get("message_count", 0),
                    last_message_time=conv.get("last_message_at"),
                    status=conv.get("status", "active"),
                    engine_mode=conv.get("engine_mode", "cs"),
                )
            )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list conversations: {str(e)}"
        )


@router.post("/conversations/{conv_id}/stop", response_model=AdminResponse)
async def stop_conversation(conv_id: int) -> AdminResponse:
    """Force stop a specific conversation.

    Marks the conversation as resolved and clears its message counter.
    Use this to manually intervene when a conversation is stuck in a loop.

    Args:
        conv_id: Conversation ID to stop
    """
    try:
        import sys
        from pathlib import Path

        scripts_dir = (
            Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
        )
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        import conversation_tracker

        success = conversation_tracker.update_status(conv_id, "resolved")

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conv_id} not found or already stopped",
            )

        return AdminResponse(
            status="success",
            message=f"Conversation {conv_id} stopped successfully",
            data={"conversation_id": conv_id, "new_status": "resolved"},
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop conversation: {str(e)}"
        )


@router.post("/pause", response_model=AdminResponse)
async def pause_cs_engine() -> AdminResponse:
    """Pause all autonomous CS engine responses.

    Sets a global flag that blocks all CS engine processing.
    Use this as an emergency stop for all automated responses.
    """
    global _PAUSE_CS_ENGINE
    _PAUSE_CS_ENGINE = True

    return AdminResponse(
        status="success",
        message="CS engine paused - all autonomous responses blocked",
        data={"paused": True},
    )


@router.post("/resume", response_model=AdminResponse)
async def resume_cs_engine() -> AdminResponse:
    """Resume CS engine responses.

    Clears the global pause flag to allow normal CS engine operation.
    """
    global _PAUSE_CS_ENGINE
    _PAUSE_CS_ENGINE = False

    return AdminResponse(
        status="success",
        message="CS engine resumed - autonomous responses enabled",
        data={"paused": False},
    )


@router.get("/status", response_model=AdminResponse)
async def get_status() -> AdminResponse:
    """Get current admin control status.

    Returns the current pause flag state and active conversation count.
    """
    try:
        import sys
        from pathlib import Path

        scripts_dir = (
            Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
        )
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        import conversation_tracker

        convs = conversation_tracker.get_active_conversations()

        return AdminResponse(
            status="success",
            message="Admin status retrieved",
            data={
                "paused": _PAUSE_CS_ENGINE,
                "active_conversations": len(convs),
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")
