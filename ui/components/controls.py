import subprocess
import threading
from pathlib import Path

import streamlit as st

_REPO_DIR = Path(__file__).resolve().parent.parent.parent  # 1ai-reach/
_PARENT_DIR = _REPO_DIR.parent  # workspace/ — scripts MUST run from here per CLAUDE.md
_PYTHON = str(_REPO_DIR / ".venv" / "bin" / "python3")
_SCRIPT_PREFIX = "1ai-reach/scripts"

PIPELINE_STEPS: list[dict[str, str]] = [
    {"key": "scrape", "label": "Scrape", "script": "scraper.py", "icon": "🔍"},
    {"key": "enrich", "label": "Enrich", "script": "enricher.py", "icon": "📧"},
    {"key": "research", "label": "Research", "script": "researcher.py", "icon": "🔬"},
    {"key": "generate", "label": "Generate", "script": "generator.py", "icon": "✍️"},
    {"key": "review", "label": "Review", "script": "reviewer.py", "icon": "👀"},
    {"key": "blast", "label": "Blast", "script": "blaster.py", "icon": "📤"},
    {
        "key": "track",
        "label": "Track Replies",
        "script": "reply_tracker.py",
        "icon": "📬",
    },
    {"key": "followup", "label": "Follow-up", "script": "followup.py", "icon": "🔁"},
    {"key": "sync", "label": "Sync Sheets", "script": "sheets_sync.py", "icon": "📊"},
]


def _init_session_state() -> None:
    if "job_running" not in st.session_state:
        st.session_state["job_running"] = False
    if "job_log" not in st.session_state:
        st.session_state["job_log"] = ""
    if "job_exit_code" not in st.session_state:
        st.session_state["job_exit_code"] = None
    if "job_label" not in st.session_state:
        st.session_state["job_label"] = ""


def _build_orchestrator_cmd(
    query: str, dry_run: bool, followup_only: bool
) -> list[str]:
    cmd = [_PYTHON, f"{_SCRIPT_PREFIX}/orchestrator.py"]
    if followup_only:
        cmd.append("--followup-only")
    elif query:
        cmd.append(query)
    if dry_run and not followup_only:
        cmd.append("--dry-run")
    return cmd


def _build_step_cmd(script: str, query: str) -> list[str]:
    cmd = [_PYTHON, f"{_SCRIPT_PREFIX}/{script}"]
    if script == "scraper.py" and query:
        cmd.append(query)
    return cmd


def _run_job(cmd: list[str], label: str) -> None:
    """Execute cmd in a background thread; writes stdout and exit code to session_state."""
    st.session_state["job_running"] = True
    st.session_state["job_log"] = ""
    st.session_state["job_exit_code"] = None
    st.session_state["job_label"] = label

    def _execute() -> None:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(_PARENT_DIR),
            )
            stdout, _ = proc.communicate(timeout=600)
            st.session_state["job_log"] = stdout or ""
            st.session_state["job_exit_code"] = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            st.session_state["job_log"] += "\n\n⏰ Job timed out after 10 minutes."
            st.session_state["job_exit_code"] = -1
        except Exception as exc:
            st.session_state["job_log"] += f"\n\n❌ Error: {exc}"
            st.session_state["job_exit_code"] = -1
        finally:
            st.session_state["job_running"] = False

    thread = threading.Thread(target=_execute, daemon=True)
    thread.start()


def render_controls() -> None:
    _init_session_state()

    query = st.text_input(
        "Search query",
        value="Digital Agency in Jakarta",
        placeholder="e.g. Coffee Shop in Surabaya",
        help="Used by scraper and orchestrator as the lead search query.",
    )

    col_opts1, col_opts2 = st.columns(2)
    with col_opts1:
        dry_run = st.checkbox("👀 Dry Run", help="Generate + review only, no sending")
    with col_opts2:
        followup_only = st.checkbox(
            "🔁 Follow-up Only", help="Run follow-up cycle only"
        )

    st.divider()

    is_running = st.session_state["job_running"]

    if st.button(
        "🚀 Run Full Pipeline",
        disabled=is_running,
        use_container_width=True,
        type="primary",
    ):
        cmd = _build_orchestrator_cmd(query, dry_run, followup_only)
        mode = "Follow-up Only" if followup_only else ("Dry Run" if dry_run else "Full")
        _run_job(cmd, f"Full Pipeline ({mode})")
        st.rerun()

    st.divider()

    st.subheader("Individual Steps")
    cols = st.columns(3)
    for idx, step in enumerate(PIPELINE_STEPS):
        col = cols[idx % 3]
        with col:
            if st.button(
                f"{step['icon']} {step['label']}",
                key=f"btn_{step['key']}",
                disabled=is_running,
                use_container_width=True,
            ):
                cmd = _build_step_cmd(step["script"], query)
                _run_job(cmd, step["label"])
                st.rerun()

    st.divider()

    if st.session_state["job_running"]:
        st.spinner(f"Running: {st.session_state['job_label']}...")
        st.info(
            f"⏳ **{st.session_state['job_label']}** is running... Refresh to check progress."
        )

    elif st.session_state["job_exit_code"] is not None:
        exit_code = st.session_state["job_exit_code"]
        label = st.session_state["job_label"]

        if exit_code == 0:
            st.success(f"✅ **{label}** completed successfully (exit code 0)")
        else:
            st.error(f"❌ **{label}** failed (exit code {exit_code})")

    if st.session_state["job_log"]:
        st.subheader("Output Log")
        st.code(st.session_state.job_log, language="text")
