from pathlib import Path
import subprocess

from oneai_reach.infrastructure.legacy.state_manager import count_by_status
from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class AutonomousService:

    def __init__(self, config: Settings):
        self.config = config
        self.loop_sleep_seconds = getattr(config, 'autonomous', type('obj', (object,), {'loop_sleep_seconds': 300})).loop_sleep_seconds
        self.min_new_leads_threshold = getattr(config, 'autonomous', type('obj', (object,), {'min_new_leads_threshold': 10})).min_new_leads_threshold
        self.scripts_dir = Path(__file__).resolve().parents[4] / 'scripts'
        self._running = {}

    def _is_running(self, name: str) -> bool:
        proc = self._running.get(name)
        if proc is None:
            return False
        if proc.poll() is None:
            return True
        del self._running[name]
        return False

    def dispatch(self, script: str, dry_run: bool = False) -> None:
        if self._is_running(script):
            logger.info(f"SKIP {script} — already running (pid {self._running[script].pid})")
            return

        if dry_run:
            logger.info(f"[DRY-RUN] Would dispatch: {script}")
            return

        script_path = self.scripts_dir / script
        if not script_path.exists():
            logger.warning(f"SKIP {script} — script file not found: {script_path}")
            return

        logger.info(f"DISPATCH {script}")
        proc = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._running[script] = proc

    def observe(self) -> dict[str, int]:
        try:
            counts = count_by_status()
        except Exception as exc:
            logger.error(f"count_by_status() failed: {exc}")
            counts = {}
        return counts

    def decide_and_act(self, counts: dict[str, int], iteration: int, dry_run: bool) -> None:
        if counts.get("new", 0) < self.min_new_leads_threshold:
            self.dispatch("strategy_agent.py", dry_run=dry_run)

        if counts.get("new", 0) > 0:
            self.dispatch("enricher.py", dry_run=dry_run)

        if counts.get("enriched", 0) > 0:
            self.dispatch("researcher.py", dry_run=dry_run)

        if counts.get("enriched", 0) > 0 or counts.get("needs_revision", 0) > 0:
            self.dispatch("generator.py", dry_run=dry_run)

        if counts.get("draft_ready", 0) > 0:
            self.dispatch("blaster.py", dry_run=dry_run)

        if counts.get("replied", 0) > 0:
            self.dispatch("closer_agent.py", dry_run=dry_run)

        if iteration % 5 == 0:
            self.dispatch("sheets_sync.py", dry_run=dry_run)
            self.dispatch("followup.py", dry_run=dry_run)

    def run_iteration(self, iteration: int, dry_run: bool = False) -> dict:
        counts = self.observe()
        total = sum(counts.values())
        logger.info(
            f"=== Iteration {iteration} | {total} total leads | Funnel: {counts or '(empty)'} ==="
        )

        self.decide_and_act(counts, iteration, dry_run=dry_run)

        return {
            "iteration": iteration,
            "total_leads": total,
            "funnel_state": counts,
            "dispatched": list(self._running.keys()),
        }
