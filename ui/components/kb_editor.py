import sys
from pathlib import Path
import json

import streamlit as st
import pandas as pd

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import kb_manager
from scripts import wa_manager

def render_kb_editor():
    st.header("📚 Knowledge Base")

    try:
        sessions = wa_manager.list_sessions()
        wa_numbers = [s.get("session_name") for s in sessions if s.get("session_name")] if sessions else ["default"]
    except Exception as e:
        st.error(f"Error loading WA sessions: {e}")
        wa_numbers = ["default"]
        
    if "default" not in wa_numbers:
        wa_numbers.insert(0, "default")

    if "kb_wa_number" not in st.session_state:
        st.session_state.kb_wa_number = wa_numbers[0]

    st.session_state.kb_wa_number = st.selectbox(
        "WA Number (Session)", 
        options=wa_numbers, 
        index=wa_numbers.index(st.session_state.kb_wa_number) if st.session_state.kb_wa_number in wa_numbers else 0,
        help="Select which WhatsApp number's KB to manage"
    )
    selected_number = st.session_state.kb_wa_number

    try:
        entries = kb_manager.get_entries(selected_number)
    except Exception as e:
        st.error(f"Failed to load KB entries: {e}")
        entries = []

    if entries:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Entries", len(entries))
        
        categories = {}
        for e in entries:
            cat = e.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            
        col2.metric("FAQs", categories.get("faq", 0))
        col3.metric("Docs", categories.get("doc", 0))
        col4.metric("Snippets", categories.get("snippet", 0))

    st.divider()

    st.subheader("🔍 Search Preview")
    search_query = st.text_input("Test KB Search (real-time)", placeholder="Type a question or keywords...")
    if search_query:
        try:
            results = kb_manager.search(selected_number, search_query, limit=5)
            if results:
                for r in results:
                    score = r.get('rank_score', 0)
                    score_display = f"(Score: {score:.2f})" if score else ""
                    with st.expander(f"[{r['category'].upper()}] {r['question']} {score_display}"):
                        st.markdown(f"**Answer:** {r['answer']}")
                        if r.get('content'):
                            st.markdown(f"**Content:** {r['content']}")
                        st.caption(f"Tags: {r.get('tags', '')} | Priority: {r.get('priority', 0)}")
            else:
                st.info("No matches found.")
        except Exception as e:
            st.error(f"Search failed: {e}")

    st.divider()

    st.subheader("📋 KB Entries")
    if entries:
        df_data = []
        for e in entries:
            ans = str(e.get("answer", ""))
            trunc_ans = ans[:100] + "..." if len(ans) > 100 else ans
            
            df_data.append({
                "ID": e["id"],
                "Category": e.get("category", ""),
                "Question": e.get("question", ""),
                "Answer": trunc_ans,
                "Tags": e.get("tags", ""),
                "Priority": e.get("priority", 0)
            })
        
        df = pd.DataFrame(df_data)
        
        st.markdown("Select a row below to **Edit** or **Delete**.")
        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun"
        )
        
        selected_rows = event.selection.rows
        if selected_rows:
            selected_idx = selected_rows[0]
            selected_id = df.iloc[selected_idx]["ID"]
            
            selected_entry = next((e for e in entries if e["id"] == selected_id), None)
            
            if selected_entry:
                st.markdown(f"### ✏️ Edit Entry #{selected_id}")
                with st.form(f"edit_form_{selected_id}"):
                    edit_cat = st.selectbox(
                        "Category", 
                        options=["faq", "doc", "snippet"],
                        index=["faq", "doc", "snippet"].index(selected_entry.get("category", "faq")) if selected_entry.get("category") in ["faq", "doc", "snippet"] else 0
                    )
                    edit_q = st.text_input("Question / Title", value=selected_entry.get("question", ""))
                    edit_a = st.text_area("Answer / Short Summary", value=selected_entry.get("answer", ""))
                    edit_c = st.text_area("Detailed Content (Optional)", value=selected_entry.get("content", ""))
                    
                    col1, col2 = st.columns(2)
                    edit_t = col1.text_input("Tags (comma separated)", value=selected_entry.get("tags", ""))
                    edit_p = col2.number_input("Priority", value=int(selected_entry.get("priority", 0)), step=1)
                    
                    submit_edit = st.form_submit_button("Update Entry", type="primary")
                    
                    if submit_edit:
                        try:
                            success = kb_manager.update_entry(
                                selected_id,
                                category=edit_cat,
                                question=edit_q,
                                answer=edit_a,
                                content=edit_c,
                                tags=edit_t,
                                priority=edit_p
                            )
                            if success:
                                st.success("Entry updated!")
                                st.rerun()
                            else:
                                st.error("Failed to update entry.")
                        except Exception as e:
                            st.error(f"Error: {e}")
                
                if st.button("🗑️ Delete Entry", type="secondary"):
                    try:
                        if kb_manager.delete_entry(selected_id):
                            st.success("Entry deleted!")
                            st.rerun()
                        else:
                            st.error("Failed to delete entry.")
                    except Exception as e:
                        st.error(f"Error: {e}")

    else:
        st.info("No KB entries found for this number.")

    st.divider()

    st.subheader("➕ Add New Entry")
    with st.form("add_kb_entry_form", clear_on_submit=True):
        add_cat = st.selectbox("Category", options=["faq", "doc", "snippet"])
        add_q = st.text_input("Question / Title *")
        add_a = st.text_area("Answer / Short Summary *")
        with st.expander("Additional Details"):
            add_c = st.text_area("Detailed Content (Optional, for docs)")
            col1, col2 = st.columns(2)
            add_t = col1.text_input("Tags (comma separated)")
            add_p = col2.number_input("Priority", value=0, step=1)
            
        submit_add = st.form_submit_button("Add Entry", type="primary")
        if submit_add:
            if not add_q or not add_a:
                st.error("Question and Answer are required fields.")
            else:
                try:
                    new_id = kb_manager.add_entry(
                        selected_number,
                        add_cat,
                        add_q,
                        add_a,
                        content=add_c,
                        tags=add_t,
                        priority=add_p
                    )
                    st.success(f"Added new entry #{new_id}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add entry: {e}")

    st.divider()

    st.subheader("🛠️ Management Actions")
    colA, colB, colC = st.columns(3)
    
    with colA:
        if st.button("🌱 Seed Default KB"):
            try:
                count = kb_manager.seed_default_kb(selected_number)
                st.success(f"Seeded {count} default entries!")
                st.rerun()
            except Exception as e:
                st.error(f"Seeding failed: {e}")
                
    with colB:
        try:
            all_entries = kb_manager.export_entries(selected_number)
            json_str = json.dumps(all_entries, indent=2)
            st.download_button(
                label="📥 Export KB (JSON)",
                data=json_str,
                file_name=f"kb_export_{selected_number}.json",
                mime="application/json"
            )
        except Exception as e:
            st.error(f"Export failed: {e}")
            
    with colC:
        uploaded_file = st.file_uploader("📤 Import KB (JSON)", type=["json"])
        if uploaded_file is not None:
            if st.button("Run Import"):
                try:
                    import_data = json.load(uploaded_file)
                    if isinstance(import_data, list):
                        count = kb_manager.import_entries(selected_number, import_data)
                        st.success(f"Successfully imported {count} entries!")
                        st.rerun()
                    else:
                        st.error("Invalid JSON format. Expected a list of entries.")
                except Exception as e:
                    st.error(f"Import failed: {e}")
