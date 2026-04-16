import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _ROOT / "scripts"


def _is_process_running(pattern: str) -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_pid(pattern: str) -> int | None:
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().splitlines()[0])
        return None
    except Exception:
        return None


def _get_process_uptime(pattern: str) -> str:
    pid = _get_pid(pattern)
    if pid is None:
        return "—"
    try:
        # /proc/<pid>/stat field 22 = starttime in clock ticks since boot
        stat = Path(f"/proc/{pid}/stat").read_text().split()
        starttime_ticks = int(stat[21])
        clk_tck = os.sysconf("SC_CLK_TCK")
        start_epoch = starttime_ticks / clk_tck
        uptime_s = time.time() - start_epoch
        if uptime_s < 60:
            return f"{int(uptime_s)}s"
        if uptime_s < 3600:
            return f"{int(uptime_s // 60)}m {int(uptime_s % 60)}s"
        hours = int(uptime_s // 3600)
        mins = int((uptime_s % 3600) // 60)
        return f"{hours}h {mins}m"
    except Exception:
        return "—"


def _http_health(url: str, timeout: int = 4) -> dict:
    try:
        import requests

        t0 = time.time()
        r = requests.get(url, timeout=timeout)
        latency = int((time.time() - t0) * 1000)
        return {
            "ok": r.status_code == 200,
            "status_code": r.status_code,
            "latency_ms": latency,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:80]}


def _read_log_tail(path: Path, lines: int = 50) -> str:
    try:
        if not path.exists():
            return "(no log file)"
        text = path.read_text(errors="replace")
        tail = text.strip().splitlines()[-lines:]
        return "\n".join(tail)
    except Exception as exc:
        return f"(error reading log: {exc})"


SERVICES = [
    {
        "key": "webhook",
        "label": "Webhook Server",
        "pattern": "webhook_server.py",
        "port": 8766,
        "health_url": "http://localhost:8766/health",
        "log_path": _ROOT / "logs" / "webhook.log",
        "start_cmd": [sys.executable, str(_ROOT / "webhook_server.py")],
    },
    {
        "key": "autonomous",
        "label": "Autonomous Loop",
        "pattern": "autonomous_loop.py",
        "port": None,
        "health_url": None,
        "log_path": _ROOT / "logs" / "autonomous.log",
        "start_cmd": [sys.executable, str(_SCRIPTS_DIR / "autonomous_loop.py")],
    },
    {
        "key": "streamlit",
        "label": "Streamlit UI",
        "pattern": "streamlit run",
        "port": 8502,
        "health_url": None,
        "log_path": _ROOT / "logs" / "streamlit.log",
        "start_cmd": None,
    },
    {
        "key": "tunnel",
        "label": "Cloudflare Tunnel",
        "pattern": "cloudflared",
        "port": None,
        "health_url": None,
        "log_path": None,
        "start_cmd": None,
    },
]


def _init_state():
    for svc in SERVICES:
        k = f"svc_action_{svc['key']}"
        if k not in st.session_state:
            st.session_state[k] = None


def render_autonomous() -> None:
    _init_state()
    st_autorefresh(interval=5000, key="autonomous_refresh")

    st.subheader("Service Status")
    st.caption("Auto-refreshes every 5 seconds")

    for svc in SERVICES:
        running = _is_process_running(svc["pattern"])
        pid = _get_pid(svc["pattern"]) if running else None
        uptime = _get_process_uptime(svc["pattern"]) if running else "—"

        health = None
        if svc["health_url"] and running:
            health = _http_health(svc["health_url"])

        col_status, col_details, col_action = st.columns([2, 3, 1])

        with col_status:
            if running:
                status_icon = "🟢"
                status_text = "Running"
                if health and not health.get("ok"):
                    status_icon = "🟡"
                    status_text = "Degraded"
            else:
                status_icon = "⚫"
                status_text = "Stopped"
            st.markdown(f"**{status_icon} {svc['label']}** — {status_text}")

        with col_details:
            details = []
            if pid:
                details.append(f"PID {pid}")
            if uptime != "—":
                details.append(f"up {uptime}")
            if svc["port"]:
                details.append(f"port {svc['port']}")
            if health and health.get("ok"):
                details.append(f"{health['latency_ms']}ms")
            elif health and not health.get("ok"):
                err = health.get("error", "unhealthy")
                details.append(f"⚠ {err}")
            st.caption(" | ".join(details) if details else "—")

        with col_action:
            if svc["start_cmd"] is None:
                st.caption("—")
            elif running:
                if st.button("⏹ Stop", key=f"stop_{svc['key']}"):
                    _stop_service(svc)
                    st.rerun()
            else:
                if st.button("▶ Start", key=f"start_{svc['key']}"):
                    _start_service(svc)
                    st.rerun()

    st.divider()

    st.subheader("Autonomous Outreach Loop")
    loop_running = _is_process_running("autonomous_loop.py")

    col_info, col_mode = st.columns([3, 2])

    with col_info:
        if loop_running:
            st.success(
                "Loop is **ACTIVE** — continuously monitoring and dispatching pipeline steps."
            )
        else:
            st.warning("Loop is **STOPPED** — no automatic outreach is happening.")

    with col_mode:
        mode = st.radio(
            "Mode",
            ["Normal", "Dry Run", "Run Once"],
            index=1 if not loop_running else 0,
            horizontal=True,
            key="autonomous_mode",
        )

    col_start, col_stop = st.columns(2)
    with col_start:
        dry = mode == "Dry Run"
        once = mode == "Run Once"
        if st.button(
            "▶ Start Autonomous Loop",
            disabled=loop_running,
            use_container_width=True,
            type="primary",
        ):
            _start_autonomous_loop(dry_run=dry, run_once=once)
            st.rerun()

    with col_stop:
        if st.button(
            "⏹ Stop Autonomous Loop",
            disabled=not loop_running,
            use_container_width=True,
        ):
            _stop_service(SERVICES[1])
            st.rerun()

    st.divider()

    st.subheader("Loop Log")
    log_lines = st.slider("Lines to show", 20, 200, 50, key="autonomous_log_lines")
    log_content = _read_log_tail(SERVICES[1]["log_path"], log_lines)
    st.code(log_content, language="log")

    st.divider()

    st.subheader("🧠 Auto-Learn & Self-Improvement")

    sys.path.insert(0, str(_SCRIPTS_DIR))
    from state_manager import get_wa_numbers

    wa_numbers = get_wa_numbers()
    cs_sessions = [s for s in wa_numbers if s.get("mode") == "cs"]

    if not cs_sessions:
        st.info(
            "No CS sessions configured. Add a WA number in CS mode to enable auto-learning."
        )
    else:
        session_names = [s["session_name"] for s in cs_sessions]
        selected_session = st.selectbox(
            "Select WA Session", session_names, key="autolearn_session"
        )

        col_report, col_improve = st.columns(2)

        with col_report:
            if st.button("📊 Generate Learning Report", use_container_width=True):
                with st.spinner("Generating report..."):
                    try:
                        result = subprocess.run(
                            [
                                sys.executable,
                                str(_SCRIPTS_DIR / "cs_learn.py"),
                                "report",
                                "--wa-number-id",
                                selected_session,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=30,
                            cwd=str(_ROOT),
                        )
                        if result.returncode == 0:
                            st.success("Report generated successfully!")
                            st.code(result.stdout, language="text")
                        else:
                            st.error(f"Report generation failed: {result.stderr}")
                    except Exception as e:
                        st.error(f"Error: {e}")

        with col_improve:
            apply_changes = st.checkbox(
                "Apply changes (not dry-run)", key="autolearn_apply"
            )
            if st.button("🚀 Run Auto-Improvement", use_container_width=True):
                with st.spinner("Running auto-improvement..."):
                    try:
                        cmd = [
                            sys.executable,
                            str(_SCRIPTS_DIR / "cs_learn.py"),
                            "improve",
                            "--wa-number-id",
                            selected_session,
                        ]
                        if apply_changes:
                            cmd.append("--apply")

                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=30,
                            cwd=str(_ROOT),
                        )
                        if result.returncode == 0:
                            st.success("Auto-improvement completed!")
                            st.code(result.stdout, language="text")
                        else:
                            st.error(f"Auto-improvement failed: {result.stderr}")
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.caption(
            "💡 Auto-learn analyzes conversation outcomes to identify winning patterns and suggest KB improvements."
        )

    st.divider()

    st.subheader("Webhook Log")
    webhook_log_lines = st.slider("Lines to show", 20, 200, 50, key="webhook_log_lines")
    webhook_log = _read_log_tail(SERVICES[0]["log_path"], webhook_log_lines)
    st.code(webhook_log, language="log")


def _start_service(svc: dict) -> None:
    cmd = svc["start_cmd"]
    if not cmd:
        return
    log_path = svc.get("log_path")
    log_dir = log_path.parent if log_path else _ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_path or (log_dir / f"{svc['key']}.log")

    try:
        with open(log_file, "a") as lf:
            subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=str(_ROOT),
            )
        st.toast(f"Started {svc['label']}", icon="✅")
    except Exception as exc:
        st.error(f"Failed to start {svc['label']}: {exc}")


def _stop_service(svc: dict) -> None:
    try:
        subprocess.run(
            ["pkill", "-f", svc["pattern"]],
            capture_output=True,
            timeout=5,
        )
        st.toast(f"Stopped {svc['label']}", icon="⏹")
    except Exception as exc:
        st.error(f"Failed to stop {svc['label']}: {exc}")


def _start_autonomous_loop(*, dry_run: bool = False, run_once: bool = False) -> None:
    log_dir = _ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "autonomous.log"

    cmd = [sys.executable, str(_SCRIPTS_DIR / "autonomous_loop.py")]
    if dry_run:
        cmd.append("--dry-run")
    if run_once:
        cmd.append("--run-once")

    try:
        with open(log_file, "a") as lf:
            lf.write(
                f"\n{'=' * 60}\n"
                f"[{datetime.now().isoformat()}] Starting autonomous loop "
                f"(dry_run={dry_run}, run_once={run_once})\n"
                f"{'=' * 60}\n"
            )
            subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=str(_ROOT),
            )
        st.toast("Autonomous loop started", icon="🚀")
    except Exception as exc:
        st.error(f"Failed to start autonomous loop: {exc}")
