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


def render_event_log():
    st_autorefresh(interval=3000, key="event_log_refresh")

    st.subheader("Event Log")

    col1, col2, col3 = st.columns(3)
    with col1:
        event_types = st.multiselect(
            "Event Types",
            [
                "webhook_received",
                "inbound_cs",
                "cs_response",
                "wa_send_attempt",
                "escalation",
                "error",
            ],
            default=[],
        )
    with col2:
        limit = st.selectbox("Show last", [50, 100, 500, 1000], index=1)
    with col3:
        auto_scroll = st.checkbox("Auto-scroll to newest", value=True)

    if not _connect:
        st.error("Database connection not available")
        return

    conn = _connect()
    try:
        query = "SELECT * FROM event_log ORDER BY id DESC LIMIT ?"
        params = (limit,)

        if event_types:
            placeholders = ",".join(["?"] * len(event_types))
            query = f"SELECT * FROM event_log WHERE event_type IN ({placeholders}) ORDER BY id DESC LIMIT ?"
            params = tuple(event_types) + (limit,)

        df = pd.read_sql_query(query, conn, params=params)

        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            def color_event(val):
                colors = {
                    "cs_response": "background-color: #d4edda",
                    "inbound_cs": "background-color: #d1ecf1",
                    "error": "background-color: #f8d7da",
                    "escalation": "background-color: #fff3cd",
                }
                return colors.get(val, "")

            st.dataframe(
                df.style.map(color_event, subset=["event_type"]),
                use_container_width=True,
                height=600,
            )
        else:
            st.info("No events found")

    finally:
        conn.close()
