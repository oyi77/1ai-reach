import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.agents.warmcall_service import WarmcallService
from oneai_reach.config.settings import get_settings
from state_manager import init_db


def main():
    parser = argparse.ArgumentParser(
        description="Warmcall engine — multi-turn follow-up sequences with intent routing"
    )
    parser.add_argument(
        "--start", action="store_true", help="Start a new warmcall sequence"
    )
    parser.add_argument("--phone", type=str, help="Contact phone number (for --start)")
    parser.add_argument("--name", type=str, help="Contact name (for --start)")
    parser.add_argument("--context", type=str, help="Business context (for --start)")
    parser.add_argument(
        "--session",
        type=str,
        default="default",
        help="WAHA session name (default: default)",
    )
    parser.add_argument("--lead-id", type=str, default=None, help="Link to lead ID")
    parser.add_argument(
        "--process-due",
        action="store_true",
        help="Process all due warmcall follow-ups",
    )
    parser.add_argument("--test", action="store_true", help="Run simulated 3-turn test")
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    service = WarmcallService(settings)

    if args.start:
        if not args.phone or not args.name:
            parser.error("--start requires --phone and --name")
        result = service.start_sequence(
            wa_number_id=args.session,
            contact_phone=args.phone,
            contact_name=args.name,
            context=args.context or "",
            lead_id=args.lead_id,
        )
        print(f"Result: {result}")

    elif args.process_due:
        result = service.process_all_due()
        print(f"Summary: {result}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
