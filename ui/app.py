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
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [
        "📊 Funnel",
        "🚀 Run Pipeline",
        "✏️ Draft Editor",
        "⚙️ Settings",
        "📱 WA Numbers",
        "💬 Conversations",
        "📚 Knowledge Base",
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
