"""
1ai-engage Streamlit WebUI Dashboard

Main entrypoint. Uses sidebar radio buttons as primary navigation.
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
from ui.components.event_log import render_event_log

st.set_page_config(
    page_title="1ai-engage Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES = [
    "📊 Funnel",
    "🚀 Run Pipeline",
    "✏️ Draft Editor",
    "⚙️ Settings",
    "📱 WA Numbers",
    "💬 Conversations",
    "📚 Knowledge Base",
    "💰 Sales Pipeline",
    "📋 Event Log",
]

if "current_page" not in st.session_state:
    st.session_state["current_page"] = PAGES[0]

with st.sidebar:
    st.markdown("### 🚀 1ai-engage")
    selected = st.radio(
        "Navigate",
        PAGES,
        index=PAGES.index(st.session_state["current_page"]),
        label_visibility="collapsed",
    )
    st.session_state["current_page"] = selected
    st.divider()

    st.markdown("**Hub Services**")
    hub_services = []
    try:
        import json

        svc_file = Path("/home/openclaw/projects/berkahkarya-hub/config/services.json")
        if svc_file.exists():
            svc = json.loads(svc_file.read_text())
            for name, key in [
                ("WAHA", "waha"),
                ("n8n", "n8n"),
                ("PaperClip", "paperclip"),
            ]:
                entry = svc.get(key, {})
                url = entry.get("domain_url") or entry.get("base_url")
                if url:
                    hub_services.append((name, url))
    except Exception:
        pass

    if hub_services:
        for name, url in hub_services:
            st.markdown(f"• [{name}]({url})")
    else:
        st.caption("Hub config not found")

    st.divider()
    st.caption("v1.0.0")

st.title(st.session_state["current_page"])

if selected == "📊 Funnel":
    render_funnel()

elif selected == "🚀 Run Pipeline":
    render_controls()

elif selected == "✏️ Draft Editor":
    render_editor()

elif selected == "⚙️ Settings":
    render_settings()

elif selected == "📱 WA Numbers":
    render_wa_numbers()

elif selected == "💬 Conversations":
    render_conversations()

elif selected == "📚 Knowledge Base":
    render_kb_editor()

elif selected == "💰 Sales Pipeline":
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from conversation_tracker import get_messages
    from state_manager import get_wa_numbers, get_all_conversation_stages
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

    by_stage = {s: [] for s in STAGE_COLS}
    for conv in convs:
        stage = conv.get("stage") or "discovery"
        if stage not in STAGE_COLS:
            stage = "discovery"
        by_stage[stage].append(conv)

    st.markdown(
        """
    <style>
    .kanban-board { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 12px; }
    .kanban-col { flex: 0 0 220px; }
    .kanban-header { position: sticky; top: 0; background: #fff; z-index: 10; padding: 4px 0 8px 0; border-bottom: 2px solid #eee; margin-bottom: 8px; }
    .kanban-cards { max-height: calc(100vh - 280px); overflow-y: auto; }
    .kanban-card { background: #f5f5f5; padding: 8px; border-radius: 6px; margin-bottom: 6px; font-size: 12px; }
    </style>
    """,
        unsafe_allow_html=True,
    )

    cols = st.columns(len(STAGE_COLS))
    for col, stage in zip(cols, STAGE_COLS):
        with col:
            count = len(by_stage[stage])
            label = stage.replace("_", " ").title()
            st.markdown(
                f"<div class='kanban-header'>"
                f"<strong>{STAGE_EMOJI.get(stage, '')} {label}</strong> <code>({count})</code>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown("<div class='kanban-cards'>", unsafe_allow_html=True)
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
                except Exception:
                    time_str = "new"

                msg = get_messages(conv["id"], limit=1)
                last_msg = msg[-1]["message_text"][:60] if msg else "..."

                st.markdown(
                    f"<div class='kanban-card'>"
                    f"<strong>{name}</strong><br/>"
                    f"<span style='color:#666'>{last_msg}...</span><br/>"
                    f"<span style='color:#999;font-size:10px'>{time_str}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)
