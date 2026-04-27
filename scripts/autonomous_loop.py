import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.agents.autonomous_service import AutonomousService
from oneai_reach.config.settings import get_settings
from state_manager import init_db


def main():
    parser = argparse.ArgumentParser(description="Autonomous OODA outreach loop")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print dispatch decisions without running scripts",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run one iteration then exit",
    )
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    service = AutonomousService(settings)

    iteration = 0
    print(
        f"Autonomous loop starting (dry_run={args.dry_run}, run_once={args.run_once}, "
        f"sleep={service.loop_sleep_seconds}s, threshold={service.min_new_leads_threshold})"
    )

    while True:
        iteration += 1
        try:
            result = service.run_iteration(iteration, dry_run=args.dry_run)
            print(f"Iteration {iteration} complete: {result}")
        except Exception as e:
            print(f"Iteration {iteration} failed: {e}")

        if args.run_once:
            print("--run-once set. Exiting after single iteration.")
            break

        print(f"Sleeping {service.loop_sleep_seconds}s before next iteration...")
        time.sleep(service.loop_sleep_seconds)


if __name__ == "__main__":
    main()
