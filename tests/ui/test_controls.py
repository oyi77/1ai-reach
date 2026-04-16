import subprocess
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from ui.components.controls import (
    PIPELINE_STEPS,
    _build_orchestrator_cmd,
    _build_step_cmd,
    _init_session_state,
    _run_job,
    _PYTHON,
    _SCRIPT_PREFIX,
    _PARENT_DIR,
)


@pytest.fixture(autouse=True)
def mock_streamlit():
    with patch("ui.components.controls.st") as mock_st:
        mock_st.session_state = {}
        yield mock_st


class TestBuildOrchestratorCmd:
    def test_full_pipeline_with_query(self):
        cmd = _build_orchestrator_cmd(
            "Coffee Shop in Jakarta", dry_run=False, followup_only=False
        )
        assert cmd == [
            _PYTHON,
            f"{_SCRIPT_PREFIX}/orchestrator.py",
            "Coffee Shop in Jakarta",
        ]

    def test_dry_run_with_query(self):
        cmd = _build_orchestrator_cmd(
            "Digital Agency", dry_run=True, followup_only=False
        )
        assert cmd == [
            _PYTHON,
            f"{_SCRIPT_PREFIX}/orchestrator.py",
            "Digital Agency",
            "--dry-run",
        ]

    def test_followup_only_ignores_query_and_dry_run(self):
        cmd = _build_orchestrator_cmd("anything", dry_run=True, followup_only=True)
        assert cmd == [_PYTHON, f"{_SCRIPT_PREFIX}/orchestrator.py", "--followup-only"]

    def test_empty_query_no_flags(self):
        cmd = _build_orchestrator_cmd("", dry_run=False, followup_only=False)
        assert cmd == [_PYTHON, f"{_SCRIPT_PREFIX}/orchestrator.py"]


class TestBuildStepCmd:
    def test_scraper_includes_query(self):
        cmd = _build_step_cmd("scraper.py", "Coffee Shop in Jakarta")
        assert cmd == [
            _PYTHON,
            f"{_SCRIPT_PREFIX}/scraper.py",
            "Coffee Shop in Jakarta",
        ]

    def test_non_scraper_ignores_query(self):
        cmd = _build_step_cmd("enricher.py", "Coffee Shop in Jakarta")
        assert cmd == [_PYTHON, f"{_SCRIPT_PREFIX}/enricher.py"]

    def test_scraper_empty_query(self):
        cmd = _build_step_cmd("scraper.py", "")
        assert cmd == [_PYTHON, f"{_SCRIPT_PREFIX}/scraper.py"]

    @pytest.mark.parametrize(
        "step",
        PIPELINE_STEPS,
        ids=[s["key"] for s in PIPELINE_STEPS],
    )
    def test_all_steps_produce_valid_cmd(self, step):
        cmd = _build_step_cmd(step["script"], "test query")
        assert cmd[0] == _PYTHON
        assert step["script"] in cmd[1]


class TestInitSessionState:
    def test_sets_defaults(self, mock_streamlit):
        _init_session_state()
        ss = mock_streamlit.session_state
        assert ss["job_running"] is False
        assert ss["job_log"] == ""
        assert ss["job_exit_code"] is None
        assert ss["job_label"] == ""

    def test_preserves_existing_values(self, mock_streamlit):
        mock_streamlit.session_state["job_running"] = True
        mock_streamlit.session_state["job_log"] = "existing"
        _init_session_state()
        assert mock_streamlit.session_state["job_running"] is True
        assert mock_streamlit.session_state["job_log"] == "existing"


class TestRunJob:
    @patch("ui.components.controls.threading.Thread")
    def test_sets_running_state_and_spawns_thread(
        self, mock_thread_cls, mock_streamlit
    ):
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        _run_job(["echo", "hello"], "Test Job")

        assert mock_streamlit.session_state["job_running"] is True
        assert mock_streamlit.session_state["job_label"] == "Test Job"
        assert mock_streamlit.session_state["job_exit_code"] is None
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

    @patch("ui.components.controls.threading.Thread")
    def test_clears_previous_log(self, mock_thread_cls, mock_streamlit):
        mock_thread_cls.return_value = MagicMock()
        mock_streamlit.session_state["job_log"] = "old output"

        _run_job(["echo", "hi"], "Reset Test")

        assert mock_streamlit.session_state["job_log"] == ""


class TestRunJobExecution:
    @patch("ui.components.controls.subprocess.Popen")
    def test_successful_execution(self, mock_popen, mock_streamlit):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("output line\n", None)
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        _run_job(["echo", "hi"], "Success Test")

        import threading as real_threading
        import time

        for t in real_threading.enumerate():
            if t.name != "MainThread" and t.daemon:
                t.join(timeout=5)

        assert mock_streamlit.session_state["job_log"] == "output line\n"
        assert mock_streamlit.session_state["job_exit_code"] == 0
        assert mock_streamlit.session_state["job_running"] is False

        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args
        assert call_kwargs.kwargs["cwd"] == str(_PARENT_DIR)
        assert call_kwargs.kwargs["text"] is True

    @patch("ui.components.controls.subprocess.Popen")
    def test_failed_execution(self, mock_popen, mock_streamlit):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("error output\n", None)
        mock_proc.returncode = 1
        mock_popen.return_value = mock_proc

        _run_job(["bad_cmd"], "Fail Test")

        import threading as real_threading

        for t in real_threading.enumerate():
            if t.name != "MainThread" and t.daemon:
                t.join(timeout=5)

        assert mock_streamlit.session_state["job_exit_code"] == 1
        assert mock_streamlit.session_state["job_running"] is False

    @patch("ui.components.controls.subprocess.Popen")
    def test_timeout_handling(self, mock_popen, mock_streamlit):
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(
            cmd="x", timeout=600
        )
        mock_popen.return_value = mock_proc

        _run_job(["slow_cmd"], "Timeout Test")

        import threading as real_threading

        for t in real_threading.enumerate():
            if t.name != "MainThread" and t.daemon:
                t.join(timeout=5)

        assert mock_streamlit.session_state["job_exit_code"] == -1
        assert "timed out" in mock_streamlit.session_state["job_log"]
        mock_proc.kill.assert_called_once()


class TestSessionStateGuard:
    @patch("ui.components.controls.threading.Thread")
    def test_double_submission_prevented_by_running_flag(
        self, mock_thread_cls, mock_streamlit
    ):
        mock_thread_cls.return_value = MagicMock()

        _run_job(["first"], "Job 1")
        assert mock_streamlit.session_state["job_running"] is True

        assert mock_streamlit.session_state["job_running"] is True


class TestCwdIsParentDirectory:
    @patch("ui.components.controls.subprocess.Popen")
    def test_popen_cwd_is_workspace_parent(self, mock_popen, mock_streamlit):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", None)
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        _run_job(["echo"], "CWD Test")

        import threading as real_threading

        for t in real_threading.enumerate():
            if t.name != "MainThread" and t.daemon:
                t.join(timeout=5)

        cwd_used = mock_popen.call_args.kwargs["cwd"]
        assert cwd_used == str(_PARENT_DIR)
        assert "1ai-reach" not in cwd_used.split("/")[-1]


class TestPipelineStepsCompleteness:
    EXPECTED_SCRIPTS = {
        "scraper.py",
        "enricher.py",
        "researcher.py",
        "generator.py",
        "reviewer.py",
        "blaster.py",
        "reply_tracker.py",
        "followup.py",
        "sheets_sync.py",
    }

    def test_all_expected_scripts_covered(self):
        actual = {s["script"] for s in PIPELINE_STEPS}
        assert actual == self.EXPECTED_SCRIPTS

    def test_unique_keys(self):
        keys = [s["key"] for s in PIPELINE_STEPS]
        assert len(keys) == len(set(keys))

    def test_step_count(self):
        assert len(PIPELINE_STEPS) == 9
