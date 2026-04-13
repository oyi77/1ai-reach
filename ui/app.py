"""
1ai-engage Streamlit WebUI Dashboard

Main entrypoint for the WebUI. Provides sidebar navigation with 4 sections:
- Funnel: Lead status visualization
- Run Pipeline: Pipeline controls and execution
- Draft Editor: Proposal draft editing interface
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import streamlit as st

from ui.components.funnel import render_funnel
from ui.components.editor import render_editor
from ui.components.controls import render_controls
from ui.components.settings import render_settings
from ui.components.conversations import render_conversations
from ui.components.wa_numbers import render_wa_numbers
from ui.components.kb_editor import render_kb_editor

# Configure page
st.set_page_config(
    page_title="1ai-engage Dashboard", layout="wide", initial_sidebar_state="expanded"
)

# Initialize global session state
if "job_running" not in st.session_state:
    st.session_state["job_running"] = False
if "job_log" not in st.session_state:
    st.session_state["job_log"] = ""
if "job_exit_code" not in st.session_state:
    st.session_state["job_exit_code"] = None
if "job_label" not in st.session_state:
    st.session_state["job_label"] = ""

# Main title
st.title("1ai-engage Dashboard")

# Sidebar navigation
with st.sidebar:
    st.header("Navigation")
    st.markdown("Use the tabs in the main area to navigate.")

# Page routing via tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
    [
        "📊 Funnel",
        "🚀 Run Pipeline",
        "✏️ Draft Editor",
        "⚙️ Settings",
        "📱 WA Numbers",
        "💬 Conversations",
        "📚 Knowledge Base",
        "💰 Sales Pipeline",
    ]
)

with tab1:
    render_funnel()

with tab2:
    render_controls()

with tab3:
    st.header("✏️ Draft Editor")
    render_editor()

with tab4:
    render_settings()

with tab5:
    render_wa_numbers()

with tab6:
    render_conversations()

with tab7:
    render_kb_editor()

with tab8:
    st.subheader("💰 Sales Pipeline")

    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from state_manager import get_wa_numbers, get_all_conversation_stages
    from conversation_tracker import get_messages
    from datetime import datetime

    sessions = get_wa_numbers()
    session_options = ["All"] + [
        s["session_name"] for s in sessions if s.get("mode") == "cs"
    ]
    selected_session = st.selectbox("Filter by Session", session_options)

    wa_filter = None if selected_session == "All" else selected_session
    convs = get_all_conversation_stages(wa_number_id=wa_filter)

    STAGE_COLS = [
        "discovery",
        "interest",
        "proposal",
        "negotiation",
        "close_won",
        "close_lost",
    ]
    STAGE_EMOJI = {
        "discovery": "🔍",
        "interest": "🤔",
        "proposal": "📋",
        "negotiation": "🤝",
        "close_won": "✅",
        "close_lost": "❌",
    }

    # Group conversations by stage
    by_stage = {s: [] for s in STAGE_COLS}
    for conv in convs:
        stage = conv.get("stage") or "discovery"
        if stage not in STAGE_COLS:
            stage = "discovery"
        by_stage[stage].append(conv)

    cols = st.columns(len(STAGE_COLS))
    for col, stage in zip(cols, STAGE_COLS):
        with col:
            count = len(by_stage[stage])
            st.markdown(
                f"**{STAGE_EMOJI.get(stage, '')} {stage.replace('_', ' ').title()}** `({count})`"
            )
            for conv in by_stage[stage]:
                phone = conv.get("contact_phone", "Unknown")
                name = conv.get("contact_name") or phone.split("@")[0]
                updated = conv.get("updated_at") or conv.get("created_at", "")
                try:
                    if updated:
                        dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                        ago = (datetime.now() - dt.replace(tzinfo=None)).days
                        time_str = f"{ago}d ago"
                    else:
                        time_str = "new"
                except:
                    time_str = "new"

                msg = get_messages(conv["id"], limit=1)
                last_msg = msg[-1]["message_text"][:50] if msg else "..."

                st.markdown(
                    f"""
                <div style="background:#f0f0f0;padding:8px;border-radius:6px;margin-bottom:6px;font-size:12px;">
                    <strong>{name}</strong><br/>
                    <span style="color:#666">{last_msg}...</span><br/>
                    <span style="color:#999;font-size:10px">{time_str}</span>
                </div>
                """,
                    unsafe_allow_html=True,
                )
