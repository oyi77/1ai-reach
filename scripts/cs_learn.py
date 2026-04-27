#!/usr/bin/env python3
"""
CS Learning CLI - Self-improvement management commands

Usage:
    python3 cs_learn.py report --wa-number-id warung_kecantikan
    python3 cs_learn.py improve --wa-number-id warung_kecantikan --apply
    python3 cs_learn.py feedback --conversation-id 123 --response "Halo" --reaction positive
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cs_self_improve import (
    analyze_and_improve,
    record_outcome_feedback,
    SelfImprovementEngine,
)


def cmd_report(args):
    """Generate learning report"""
    engine = SelfImprovementEngine(args.wa_number_id)
    report = engine.generate_weekly_report()

    print(f"\n📊 Learning Report: {args.wa_number_id}")
    print("=" * 50)
    print(f"\n📈 Funnel Summary (7 days):")
    for status, count in report["funnel_summary"].items():
        print(f"  - {status}: {count}")

    print(f"\n🏆 Winning Patterns ({len(report['winning_patterns'])}):")
    for p in report["winning_patterns"][:5]:
        print(f"  ✓ {p['pattern']}: score={p['score']:.2f}, uses={p['uses']}")

    print(f"\n⚠️ Low Performers ({len(report['low_performers'])}):")
    for lp in report["low_performers"][:5]:
        print(f"  ✗ {lp['question'][:50]}... (score={lp['score']:.2f})")

    print(f"\n💡 Suggested New KB Entries ({len(report['suggested_entries'])}):")
    for s in report["suggested_entries"][:5]:
        print(f'  ? "{s["question"]}" (asked {s["frequency"]} times)')

    if report["recommendations"]:
        print(f"\n🎯 Recommendations:")
        for r in report["recommendations"]:
            print(f"  • {r}")


def cmd_improve(args):
    """Apply automatic improvements"""
    print(f"🧠 Running self-improvement for {args.wa_number_id}...")

    engine = SelfImprovementEngine(args.wa_number_id)
    results = engine.apply_learnings(dry_run=not args.apply)

    print(f"\n✅ Analysis Complete:")
    print(f"  Patterns to add: {results['patterns_added']}")
    print(f"  Suggestions created: {results['suggestions_created']}")

    if results["errors"]:
        print(f"\n⚠️ Errors:")
        for e in results["errors"]:
            print(f"  ! {e}")

    if not args.apply:
        print(f"\nℹ️ Dry run mode - no changes applied")
        print(f"   Run with --apply to actually make changes")


def cmd_feedback(args):
    """Record outcome feedback"""
    record_outcome_feedback(
        conversation_id=args.conversation_id,
        response_text=args.response,
        user_reaction=args.reaction,
        outcome=args.outcome,
    )
    print(f"✅ Feedback recorded for conversation {args.conversation_id}")


def main():
    parser = argparse.ArgumentParser(description="CS Learning System")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate learning report")
    report_parser.add_argument("--wa-number-id", default="warung_kecantikan")
    report_parser.set_defaults(func=cmd_report)

    # Improve command
    improve_parser = subparsers.add_parser("improve", help="Apply improvements")
    improve_parser.add_argument("--wa-number-id", default="warung_kecantikan")
    improve_parser.add_argument(
        "--apply", action="store_true", help="Actually apply changes"
    )
    improve_parser.set_defaults(func=cmd_improve)

    # Feedback command
    feedback_parser = subparsers.add_parser("feedback", help="Record feedback")
    feedback_parser.add_argument("--conversation-id", type=int, required=True)
    feedback_parser.add_argument("--response", required=True)
    feedback_parser.add_argument(
        "--reaction",
        choices=["positive", "negative", "neutral", "no_reply"],
        required=True,
    )
    feedback_parser.add_argument(
        "--outcome",
        choices=["purchase", "interested", "abandoned", "escalated"],
        required=True,
    )
    feedback_parser.set_defaults(func=cmd_feedback)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
