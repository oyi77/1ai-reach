import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from scripts.state_manager import _connect
except ImportError:
    _connect = None

try:
    from scripts.conversation_tracker import update_status, escalate, get_messages
except ImportError:

    def update_status(cid, status):
        return False

    def escalate(cid, reason):
        return False

    def get_messages(cid):
        return []


try:
    from scripts.wa_manager import list_sessions
except ImportError:
    list_sessions = None


def _get_all_conversations():
    if not _connect:
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY last_message_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        st.error(f"Error fetching conversations: {e}")
        return []
    finally:
        conn.close()


def render_conversations():
    # Auto-refresh every 5 seconds
    st_autorefresh(interval=5000, key="conversation_refresh")

    # Header removed - page title handled by app.py

    # Fetch data
    all_convs = _get_all_conversations()

    if not all_convs:
        st.info("No conversations found in the database.")
        return

    # Compute Stats
    total_active = sum(1 for c in all_convs if c.get("status") == "active")
    total_escalated = sum(1 for c in all_convs if c.get("status") == "escalated")

    mode_counts = {}
    for c in all_convs:
        mode = c.get("engine_mode", "unknown")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1

    # Stats Bar
    st.subheader("Overview")
    stats_cols = st.columns(3 + len(mode_counts))
    stats_cols[0].metric("Total Active", total_active)
    stats_cols[1].metric("Total Escalated", total_escalated)
    stats_cols[2].metric("Total Conversations", len(all_convs))

    for i, (m, count) in enumerate(mode_counts.items()):
        stats_cols[3 + i].metric(f"Mode: {m}", count)

    st.divider()

    # Filter Bar
    st.subheader("Filters")
    fcol1, fcol2, fcol3 = st.columns(3)

    # 1. Number Selector
    available_numbers = ["all"]
    if list_sessions:
        try:
            sessions = list_sessions()
            for s in sessions:
                name = s.get("session_name")
                if name and name not in available_numbers:
                    available_numbers.append(name)
        except Exception:
            pass
    # Add any wa_number_id found in db not already in list
    for c in all_convs:
        num = c.get("wa_number_id")
        if num and num not in available_numbers:
            available_numbers.append(num)

    with fcol1:
        selected_number = st.selectbox("WA Number", available_numbers, index=0)

    with fcol2:
        selected_status = st.selectbox(
            "Status", ["all", "active", "resolved", "escalated", "cold"], index=0
        )

    with fcol3:
        selected_mode = st.selectbox(
            "Engine Mode", ["all", "cs", "warmcall", "cold"], index=0
        )

    # Apply filters
    filtered_convs = [
        c
        for c in all_convs
        if (selected_number == "all" or c.get("wa_number_id") == selected_number)
        and (selected_status == "all" or c.get("status") == selected_status)
        and (selected_mode == "all" or c.get("engine_mode") == selected_mode)
    ]

    st.write(f"Showing {len(filtered_convs)} conversation(s)")

    if not filtered_convs:
        st.info("No conversations match the current filters.")
        return

    # Conversation List (Expanders)
    for conv in filtered_convs:
        cid = conv.get("id")
        c_phone = conv.get("contact_phone", "Unknown")
        c_name = conv.get("contact_name") or "Unknown"
        status = conv.get("status", "unknown")
        mode = conv.get("engine_mode", "unknown")
        msg_count = conv.get("message_count", 0)
        last_msg = conv.get("last_message_at", "Never")

        # Determine emoji indicator based on status
        status_emoji = (
            "🟢"
            if status == "active"
            else "🔴"
            if status == "escalated"
            else "⚪"
            if status == "cold"
            else "✅"
        )

        expander_label = f"{status_emoji} {c_name} ({c_phone}) | Mode: {mode} | Msgs: {msg_count} | Last: {last_msg}"

        with st.expander(expander_label):
            # Layout: Chat history on top, actions below
            st.markdown(
                f"**Conversation ID:** `{cid}` | **Status:** `{status}` | **WA Number:** `{conv.get('wa_number_id', 'unknown')}`"
            )

            # Chat messages
            messages = get_messages(cid)
            if not messages:
                st.write("No messages recorded.")
            else:
                chat_container = st.container(height=400)
                with chat_container:
                    for msg in messages:
                        direction = msg.get("direction", "inbound")
                        text = msg.get("message_text", "")
                        timestamp = msg.get("timestamp", "")

                        if direction in ["inbound", "in"]:
                            # Customer message - Left, Gray
                            st.markdown(
                                f"""
                            <div style="background-color: #2b2b2b; color: #f0f0f0; padding: 10px; border-radius: 10px; margin: 5px 0; max-width: 80%;">
                                <small style="color: #aaaaaa;">{timestamp}</small><br>
                                {text}
                            </div>
                            """,
                                unsafe_allow_html=True,
                            )
                        else:
                            # Agent message - Right, Blue
                            st.markdown(
                                f"""
                            <div style="background-color: #0084ff; color: white; padding: 10px; border-radius: 10px; margin: 5px 0; max-width: 80%; margin-left: auto;">
                                <small style="color: #cccccc;">{timestamp}</small><br>
                                {text}
                            </div>
                            """,
                                unsafe_allow_html=True,
                            )

            st.divider()

            # Action buttons
            st.markdown("### Actions")
            col_a, col_b, col_c = st.columns([1, 2, 1])

            with col_a:
                if st.button(
                    "✅ Resolve", key=f"resolve_{cid}", disabled=status == "resolved"
                ):
                    if update_status(cid, "resolved"):
                        st.success("Resolved!")
                        st.rerun()
                    else:
                        st.error("Failed to resolve.")

            with col_b:
                reason = st.text_input(
                    "Escalation Reason",
                    key=f"reason_{cid}",
                    placeholder="Why are you escalating this?",
                )

            with col_c:
                if st.button(
                    "🚨 Escalate", key=f"escalate_{cid}", disabled=status == "escalated"
                ):
                    if not reason:
                        st.warning("Please provide a reason to escalate.")
                    else:
                        if escalate(cid, reason):
                            st.success("Escalated!")
                            st.rerun()
                        else:
                            st.error("Failed to escalate.")
