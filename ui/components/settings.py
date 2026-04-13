import os
from pathlib import Path
import sys
import streamlit as st

# Ensure scripts/ is importable when run from ui/ subdirectory
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import config  # noqa: E402

ENV_PATH = _ROOT / ".env"


def read_env() -> dict[str, str]:
    if not os.path.exists(ENV_PATH):
        return {}
    env_vars = {}
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, val = line.split("=", 1)
                    env_vars[key.strip()] = val.strip().strip("'\"")
    return env_vars


def write_env(updates: dict[str, str]) -> None:
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    keys_found = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                lines[i] = f"{key}={updates[key]}\n"
                keys_found.add(key)

    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    for key, val in updates.items():
        if key not in keys_found and val is not None and val != "":
            lines.append(f"{key}={val}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


def render_settings():
    st.header("⚙️ Settings")

    env_vars = read_env()

    with st.form("settings_form"):
        with st.expander("Google & Sheets", expanded=True):
            sheet_id = st.text_input(
                "SHEET_ID",
                value=env_vars.get("SHEET_ID", config.SHEET_ID),
            )
            google_api_key = st.text_input(
                "GOOGLE_API_KEY",
                value=env_vars.get("GOOGLE_API_KEY", config.GOOGLE_API_KEY),
                type="password",
            )

        with st.expander("Email Settings"):
            gmail_account = st.text_input(
                "GMAIL_ACCOUNT",
                value=env_vars.get("GMAIL_ACCOUNT", config.GMAIL_ACCOUNT),
            )
            brevo_api_key = st.text_input(
                "BREVO_API_KEY",
                value=env_vars.get("BREVO_API_KEY", config.BREVO_API_KEY),
                type="password",
            )

            col1, col2 = st.columns([3, 1])
            with col1:
                smtp_host = st.text_input(
                    "SMTP_HOST",
                    value=env_vars.get("SMTP_HOST", config.SMTP_HOST),
                )
            with col2:
                smtp_port_str = env_vars.get("SMTP_PORT", str(config.SMTP_PORT))
                smtp_port = st.number_input(
                    "SMTP_PORT",
                    value=int(smtp_port_str)
                    if smtp_port_str.isdigit()
                    else config.SMTP_PORT,
                    step=1,
                )

            smtp_user = st.text_input(
                "SMTP_USER",
                value=env_vars.get("SMTP_USER", config.SMTP_USER),
            )
            smtp_password = st.text_input(
                "SMTP_PASSWORD",
                value=env_vars.get("SMTP_PASSWORD", config.SMTP_PASSWORD),
                type="password",
            )
            smtp_from = st.text_input(
                "SMTP_FROM",
                value=env_vars.get("SMTP_FROM", config.SMTP_FROM),
            )

        with st.expander("WhatsApp / WAHA"):
            waha_url = st.text_input(
                "WAHA_URL",
                value=env_vars.get("WAHA_URL", config.WAHA_URL),
            )
            waha_api_key = st.text_input(
                "WAHA_API_KEY",
                value=env_vars.get("WAHA_API_KEY", config.WAHA_API_KEY),
                type="password",
            )
            waha_direct_url = st.text_input(
                "WAHA_DIRECT_URL",
                value=env_vars.get("WAHA_DIRECT_URL", config.WAHA_DIRECT_URL),
            )
            waha_direct_api_key = st.text_input(
                "WAHA_DIRECT_API_KEY",
                value=env_vars.get("WAHA_DIRECT_API_KEY", config.WAHA_DIRECT_API_KEY),
                type="password",
            )
            waha_session = st.text_input(
                "WAHA_SESSION",
                value=env_vars.get("WAHA_SESSION", config.WAHA_SESSION),
            )
            waha_own_number = st.text_input(
                "WAHA_OWN_NUMBER",
                value=env_vars.get("WAHA_OWN_NUMBER", config.WAHA_OWN_NUMBER),
            )

        with st.expander("AI Models"):
            col1, col2 = st.columns(2)
            gen_model_val = env_vars.get("GENERATOR_MODEL", config.GENERATOR_MODEL)
            rev_model_val = env_vars.get("REVIEWER_MODEL", config.REVIEWER_MODEL)

            gen_options = ["sonnet", "haiku", "opus", "gemini"]
            rev_options = ["sonnet", "haiku", "opus"]

            with col1:
                generator_model = st.selectbox(
                    "GENERATOR_MODEL",
                    gen_options,
                    index=gen_options.index(gen_model_val)
                    if gen_model_val in gen_options
                    else 0,
                )
            with col2:
                reviewer_model = st.selectbox(
                    "REVIEWER_MODEL",
                    rev_options,
                    index=rev_options.index(rev_model_val)
                    if rev_model_val in rev_options
                    else 0,
                )

        with st.expander("Telegram"):
            telegram_bot_token = st.text_input(
                "TELEGRAM_BOT_TOKEN",
                value=env_vars.get("TELEGRAM_BOT_TOKEN", config.TELEGRAM_BOT_TOKEN),
                type="password",
            )
            telegram_chat_id = st.text_input(
                "TELEGRAM_CHAT_ID",
                value=env_vars.get("TELEGRAM_CHAT_ID", config.TELEGRAM_CHAT_ID),
            )

        with st.expander("Pipeline Configuration"):
            col1, col2 = st.columns(2)

            loop_str = env_vars.get(
                "LOOP_SLEEP_SECONDS", str(config.LOOP_SLEEP_SECONDS)
            )
            min_leads_str = env_vars.get(
                "MIN_NEW_LEADS_THRESHOLD", str(config.MIN_NEW_LEADS_THRESHOLD)
            )

            with col1:
                loop_sleep = st.number_input(
                    "LOOP_SLEEP_SECONDS",
                    value=int(loop_str)
                    if loop_str.isdigit()
                    else config.LOOP_SLEEP_SECONDS,
                    step=1,
                )
            with col2:
                min_new_leads = st.number_input(
                    "MIN_NEW_LEADS_THRESHOLD",
                    value=int(min_leads_str)
                    if min_leads_str.isdigit()
                    else config.MIN_NEW_LEADS_THRESHOLD,
                    step=1,
                )

            payment_link = st.text_input(
                "PAYMENT_LINK",
                value=env_vars.get("PAYMENT_LINK", config.PAYMENT_LINK),
            )
            calendly_link = st.text_input(
                "CALENDLY_LINK",
                value=env_vars.get("CALENDLY_LINK", config.CALENDLY_LINK),
            )

        with st.expander("Hub / Integrations"):
            hub_url = st.text_input(
                "HUB_URL",
                value=env_vars.get("HUB_URL", config.HUB_URL),
            )
            hub_api_key = st.text_input(
                "HUB_API_KEY",
                value=env_vars.get("HUB_API_KEY", config.HUB_API_KEY),
                type="password",
            )
            n8n_meeting = st.text_input(
                "N8N_MEETING_WF",
                value=env_vars.get("N8N_MEETING_WF", config.N8N_MEETING_WF),
            )

            paperclip_url = st.text_input(
                "PAPERCLIP_URL",
                value=env_vars.get("PAPERCLIP_URL", config.PAPERCLIP_URL),
            )
            paperclip_company = st.text_input(
                "PAPERCLIP_COMPANY_ID",
                value=env_vars.get("PAPERCLIP_COMPANY_ID", config.PAPERCLIP_COMPANY_ID),
            )
            paperclip_agent = st.text_input(
                "PAPERCLIP_AGENT_CMO",
                value=env_vars.get("PAPERCLIP_AGENT_CMO", config.PAPERCLIP_AGENT_CMO),
            )

        st.divider()
        submitted = st.form_submit_button(
            "Save Settings", type="primary", use_container_width=True
        )

        if submitted:
            updates = {
                "SHEET_ID": sheet_id,
                "GOOGLE_API_KEY": google_api_key,
                "GMAIL_ACCOUNT": gmail_account,
                "BREVO_API_KEY": brevo_api_key,
                "SMTP_HOST": smtp_host,
                "SMTP_PORT": str(smtp_port),
                "SMTP_USER": smtp_user,
                "SMTP_PASSWORD": smtp_password,
                "SMTP_FROM": smtp_from,
                "WAHA_URL": waha_url,
                "WAHA_API_KEY": waha_api_key,
                "WAHA_DIRECT_URL": waha_direct_url,
                "WAHA_DIRECT_API_KEY": waha_direct_api_key,
                "WAHA_SESSION": waha_session,
                "WAHA_OWN_NUMBER": waha_own_number,
                "GENERATOR_MODEL": generator_model,
                "REVIEWER_MODEL": reviewer_model,
                "TELEGRAM_BOT_TOKEN": telegram_bot_token,
                "TELEGRAM_CHAT_ID": telegram_chat_id,
                "LOOP_SLEEP_SECONDS": str(loop_sleep),
                "MIN_NEW_LEADS_THRESHOLD": str(min_new_leads),
                "PAYMENT_LINK": payment_link,
                "CALENDLY_LINK": calendly_link,
                "HUB_URL": hub_url,
                "HUB_API_KEY": hub_api_key,
                "N8N_MEETING_WF": n8n_meeting,
                "PAPERCLIP_URL": paperclip_url,
                "PAPERCLIP_COMPANY_ID": paperclip_company,
                "PAPERCLIP_AGENT_CMO": paperclip_agent,
            }

            try:
                write_env(updates)
                st.success("✅ Settings saved successfully to .env")
            except Exception as e:
                st.error(f"❌ Failed to save settings: {e}")
