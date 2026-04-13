import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from scripts import wa_manager
    from scripts import state_manager
except ImportError:
    st.error(
        "Failed to import WA Manager or State Manager. Make sure you are running from the root directory."
    )
    wa_manager = None
    state_manager = None


def render_wa_numbers():
    st.header("📱 WA Numbers")

    if not wa_manager or not state_manager:
        st.warning("Dependencies not loaded.")
        return

    st.markdown("### Manage WhatsApp Sessions")

    try:
        sessions = wa_manager.list_sessions()
    except Exception as e:
        st.error(f"Failed to fetch sessions: {e}")
        sessions = []

    if sessions:
        for idx, session in enumerate(sessions):
            name = session.get("session_name", "unknown")
            status = session.get("status", "UNKNOWN").upper()
            phone = session.get("phone", "")
            label = session.get("label", "")
            mode = session.get("mode", "cs")

            if status == "WORKING":
                status_icon = "🟢"
            elif status == "SCAN_QR_CODE":
                status_icon = "🟡"
            else:
                status_icon = "🔴"

            with st.expander(
                f"{status_icon} {name} - {label} ({phone})", expanded=True
            ):
                col1, col2, col3 = st.columns([2, 1, 1])

                with col1:
                    st.write(f"**Status:** {status}")
                    st.write(f"**Phone:** {phone}")
                    st.write(f"**Label:** {label}")

                with col2:
                    modes = ["cs", "warmcall", "cold"]
                    try:
                        mode_idx = modes.index(mode)
                    except ValueError:
                        mode_idx = 0

                    new_mode = st.selectbox(
                        "Mode", modes, index=mode_idx, key=f"mode_{name}_{idx}"
                    )

                    if new_mode != mode:
                        try:
                            state_manager.upsert_wa_number(name, mode=new_mode)
                            st.success("Mode updated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update mode: {e}")

                with col3:
                    st.write("**Controls**")
                    if status == "SCAN_QR_CODE":
                        if st.button("Show QR", key=f"qr_{name}_{idx}"):
                            try:
                                qr_data = wa_manager.get_qr_code(name)
                                if isinstance(qr_data, bytes):
                                    st.image(qr_data, caption=f"Scan QR for {name}")
                                else:
                                    st.error(f"Could not load QR code: {qr_data}")
                            except Exception as e:
                                st.error(f"Failed to fetch QR code: {e}")

                    if st.button("Start", key=f"start_{name}_{idx}"):
                        try:
                            wa_manager.start_session(name)
                            st.success(f"Started session {name}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to start: {e}")

                    if st.button("Stop", key=f"stop_{name}_{idx}"):
                        try:
                            wa_manager.stop_session(name)
                            st.success(f"Stopped session {name}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to stop: {e}")

                    if st.button("Delete", type="primary", key=f"del_{name}_{idx}"):
                        try:
                            wa_manager.delete_session(name)
                            st.success(f"Deleted session {name}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete: {e}")
    else:
        st.info("No WA sessions found.")

    if st.button("Refresh Sessions"):
        st.rerun()

    st.markdown("---")

    st.markdown("### Add New WA Number")
    with st.form("add_wa_number_form"):
        new_name = st.text_input("Session Name (internal ID)", help="e.g. sales_bot_1")
        new_phone = st.text_input(
            "Phone Number", help="Include country code, e.g. +628123..."
        )
        new_label = st.text_input("Label", help="Friendly display name")
        new_mode = st.selectbox("Mode", ["cs", "warmcall", "cold"])
        new_persona = st.text_area("Persona", help="Instructions for this bot")

        submitted = st.form_submit_button("Create Session")

        if submitted:
            if not new_name:
                st.error("Session Name is required.")
            else:
                try:
                    result = wa_manager.create_session(
                        session_name=new_name,
                        phone=new_phone,
                        label=new_label,
                        mode=new_mode,
                        persona=new_persona,
                    )
                    st.success(
                        f"Created session '{new_name}'. Please click 'Refresh' if it doesn't appear immediately."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to create session: {e}")
