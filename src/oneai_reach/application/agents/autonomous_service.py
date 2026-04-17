"""Autonomous OODA loop - observe funnel state, orient, decide, act.

Replaces the old sequential orchestrator.py with a continuous loop that
evaluates the funnel on every iteration and dispatches only what's needed.

The OODA loop (Observe-Orient-Decide-Act) continuously:
1. Observes current funnel state (lead counts by status)
2. Orients based on configured thresholds
3. Decides which scripts to dispatch
4. Acts by launching scripts non-blocking
"""

import subprocess
import sys
from pathlib import Path

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class AutonomousService:
    """Service for autonomous OODA loop orchestration."""

    def __init__(self, config: Settings):
        """Initialize autonomous service.

        Args:
            config: Application settings
        """
        self.config = config
        self.loop_sleep_seconds = config.pipeline.loop_sleep_seconds
        self.min_new_leads_threshold = config.pipeline.min_new_leads_threshold
        self.scripts_dir = Path(config.database.data_dir).parent / "scripts"
        self._running: dict[str, subprocess.Popen] = {}

    def _is_running(self, name: str) -> bool:
        """Return True if *name* was dispatched and hasn't exited yet.

        Args:
            name: Script name

        Returns:
            True if script is still running
        """
        proc = self._running.get(name)
        if proc is None:
            return False
        if proc.poll() is None:
            return True
        del self._running[name]
        return False

    def dispatch(self, script: str, *, dry_run: bool = False) -> None:
        """Launch *script* non-blocking via Popen. Skip if already running.

        Args:
            script: Script filename to dispatch
            dry_run: If True, only log what would be dispatched
        """
        if self._is_running(script):
            logger.info(
                f"SKIP {script} — already running (pid {self._running[script].pid})"
            )
            return

        if dry_run:
            logger.info(f"[DRY-RUN] Would dispatch: {script}")
            return

        script_path = self.scripts_dir / script
        if not script_path.exists():
            logger.warning(f"SKIP {script} — script file not found: {script_path}")
            return

        logger.info(f"DISPATCH {script}")
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self._running[script] = proc
        except Exception as e:
            logger.error(f"Failed to dispatch {script}: {e}")
            raise ExternalAPIError(
                service="autonomous_service",
                endpoint="/dispatch",
                status_code=0,
                reason=str(e),
            )

    def observe(self) -> dict[str, int]:
        """Query funnel state from SQLite.

        Returns:
            dict with lead counts by status
        """
        try:
            from state_manager import count_by_status

            counts = count_by_status()
            logger.info(f"Observed funnel state: {counts}")
            return counts
        except Exception as e:
            logger.error(f"count_by_status() failed: {e}")
            return {}

    def decide_and_act(
        self, counts: dict[str, int], iteration: int, *, dry_run: bool = False
    ) -> None:
        """Full funnel decision tree - dispatch scripts based on counts.

        Args:
            counts: Lead counts by status
            iteration: Current iteration number
            dry_run: If True, only log decisions
        """
        logger.info(f"[Iteration {iteration}] Deciding based on funnel state")

        if counts.get("new", 0) < self.min_new_leads_threshold:
            self.dispatch("strategy_agent.py", dry_run=dry_run)

        if counts.get("new", 0) > 0:
            self.dispatch("enricher.py", dry_run=dry_run)

        if counts.get("enriched", 0) > 0:
            self.dispatch("researcher.py", dry_run=dry_run)

        if counts.get("draft_ready", 0) > 0:
            self.dispatch("generator.py", dry_run=dry_run)

        if counts.get("needs_revision", 0) > 0:
            self.dispatch("generator.py", dry_run=dry_run)

        if counts.get("reviewed", 0) > 0:
            self.dispatch("blaster.py", dry_run=dry_run)

        if counts.get("followed_up", 0) > 0:
            self.dispatch("reply_tracker.py", dry_run=dry_run)

        if counts.get("replied", 0) > 0:
            self.dispatch("converter.py", dry_run=dry_run)

        if counts.get("meeting_booked", 0) > 0:
            self.dispatch("followup.py", dry_run=dry_run)

        self.dispatch("sheets_sync.py", dry_run=dry_run)

    def run(self, *, dry_run: bool = False, run_once: bool = False) -> None:
        """Main OODA loop - continuous observation and action.

        Args:
            dry_run: If True, only log decisions without dispatching
            run_once: If True, run single iteration then exit
        """
        iteration = 0
        try:
            while True:
                iteration += 1
                logger.info(f"=== OODA Loop Iteration {iteration} ===")

                counts = self.observe()
                self.decide_and_act(counts, iteration, dry_run=dry_run)

                if run_once:
                    logger.info("Run-once mode: exiting after single iteration")
                    break

                logger.info(f"Sleeping for {self.loop_sleep_seconds} seconds...")
                import time

                time.sleep(self.loop_sleep_seconds)

        except KeyboardInterrupt:
            logger.info("Autonomous loop interrupted by user")
        except Exception as e:
            logger.error(f"Autonomous loop failed: {e}")
            raise ExternalAPIError(
                service="autonomous_service",
                endpoint="/run",
                status_code=0,
                reason=str(e),
            )
