import pandas as pd
import streamlit as st
import os

from scripts.config import LEADS_FILE


def render_funnel(df=None):
    st.header("📊 Funnel")

    if df is None:
        if not os.path.exists(LEADS_FILE) or os.path.getsize(LEADS_FILE) == 0:
            st.info("No leads found.")
            return
        df = pd.read_csv(LEADS_FILE)

    if df.empty:
        st.info("No leads found.")
        return

    if "status" in df.columns:
        counts = df["status"].value_counts().to_dict()
    else:
        counts = {}

    key_stages = [
        "new",
        "enriched",
        "draft_ready",
        "reviewed",
        "contacted",
        "replied",
        "meeting_booked",
        "won",
    ]

    cols = st.columns(len(key_stages))
    for col, stage in zip(cols, key_stages):
        count = counts.get(stage, 0)
        col.metric(label=stage.replace("_", " ").title(), value=count)

    st.subheader("All Statuses Overview")
    if counts:
        chart_data = pd.DataFrame(
            list(counts.items()), columns=["Status", "Count"]
        ).set_index("Status")
        st.bar_chart(chart_data)
    else:
        st.info("No status data available.")

    with st.expander("ℹ️ Understanding Funnel Stages"):
        st.markdown("""
### How This Funnel Works

The numbers above show **where leads are RIGHT NOW** — not a cumulative total.
Leads move **forward** through the pipeline: once a lead reaches "Contacted",
it is no longer counted as "Enriched" or "Draft Ready". So if you see
**Enriched = 0** and **Contacted = 58**, it means all 58 enriched leads
successfully progressed to the Contacted stage. 🎉

---

### Pipeline Stages Explained

| Stage | What it means |
|---|---|
| **New** | Lead was just scraped (Google Places, Vibe Prospecting, etc.). No contact info found yet. |
| **Enriched** | Email and/or phone number found. Ready for proposal generation. |
| **Draft Ready** | AI-generated proposal written, waiting for quality review. |
| **Reviewed** | Proposal passed the AI quality gate (score ≥ 6/10). Ready to send. |
| **Contacted** | Email and/or WhatsApp message sent. Waiting for a reply. |
| **Followed Up** | Follow-up message sent 7 days after first contact. |
| **Replied** | The prospect replied! 🔥 Meeting invite has been triggered. |
| **Meeting Booked** | Meeting scheduled. Actively in conversation. |
| **Won** | Deal closed. 🏆 |
| **Lost** | Prospect declined or went cold after a reply. |
| **Cold** | No reply after follow-up (14+ days). Automatically marked cold. |
| **Unsubscribed** | Prospect asked to stop receiving messages. Permanently excluded. |

---

### Tips

- **Enriched = 0 but Contacted = 58?** All enriched leads moved forward — that's great!
- **New leads piling up?** The pipeline may be paused. Try *Run Pipeline → Enrich*.
- **Replied leads?** Check your email and WhatsApp. A personal follow-up seals the deal.
- **Cold leads?** They can be manually reset to "new" to re-enter the pipeline.
        """)
