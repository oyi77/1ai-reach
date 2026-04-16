"""
Brain-driven niche targeting agent.

Queries the BerkahKarya hub brain for outreach win data to decide which
vertical converts best, then invokes the scraper for that vertical.

Falls back to a simple rotation through DEFAULT_VERTICALS when the brain
is offline or returns no actionable data.

Usage (from parent dir of 1ai-reach):
    python3 1ai-reach/scripts/strategy_agent.py --dry-run
    python3 1ai-reach/scripts/strategy_agent.py --vertical "Coffee Shop"
    python3 1ai-reach/scripts/strategy_agent.py --location Bandung --count 30
"""

import argparse
import json
import logging
import subprocess
import sys

from config import DEFAULT_VERTICALS, _ROOT

import brain_client

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROTATION_FILE = _ROOT / ".sisyphus" / "strategy_rotation.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [strategy] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rotation state
# ---------------------------------------------------------------------------


def _load_rotation_index() -> int:
    """Load the last rotation index from disk, or 0 if missing."""
    try:
        data = json.loads(_ROTATION_FILE.read_text())
        return int(data.get("index", 0))
    except Exception:
        return 0


def _save_rotation_index(index: int) -> None:
    """Persist the current rotation index."""
    _ROTATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ROTATION_FILE.write_text(json.dumps({"index": index}))


def next_from_rotation() -> str:
    """Pick the next vertical from DEFAULT_VERTICALS via round-robin."""
    idx = _load_rotation_index()
    vertical = DEFAULT_VERTICALS[idx % len(DEFAULT_VERTICALS)]
    _save_rotation_index((idx + 1) % len(DEFAULT_VERTICALS))
    return vertical


# ---------------------------------------------------------------------------
# Brain-based decision
# ---------------------------------------------------------------------------


def _extract_vertical_from_brain(text: str) -> str | None:
    """
    Try to extract a vertical name from brain strategy text.

    Looks for mentions of DEFAULT_VERTICALS (case-insensitive) in the text
    and returns the one that appears most frequently, indicating it converts best.
    """
    if not text:
        return None

    text_lower = text.lower()
    counts: dict[str, int] = {}
    for v in DEFAULT_VERTICALS:
        n = text_lower.count(v.lower())
        if n > 0:
            counts[v] = n

    if not counts:
        return None

    return max(counts, key=counts.get)  # type: ignore[arg-type]


def decide_vertical() -> str:
    """
    1. Query brain for 'outreach_win' data to find best-converting vertical.
    2. Parse response to extract the vertical name.
    3. Fall back to rotation if brain is offline or unparseable.
    """
    try:
        results = brain_client.search("outreach_win best converting vertical", limit=5)
        if results:
            combined = " ".join(r.get("content", "") for r in results)
            found = _extract_vertical_from_brain(combined)
            if found:
                log.info("Brain recommends vertical: %s (from win data)", found)
                return found

        strategy = brain_client.get_strategy("outreach")
        if strategy:
            found = _extract_vertical_from_brain(strategy)
            if found:
                log.info("Brain recommends vertical: %s (from strategy)", found)
                return found

        log.info("Brain returned no actionable vertical data, using rotation.")
    except Exception as e:
        log.warning("Brain query failed: %s — using rotation fallback.", e)

    vertical = next_from_rotation()
    log.info("Rotation fallback selected: %s", vertical)
    return vertical


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------


def run_scraping(
    vertical: str,
    location: str = "Jakarta",
    n: int = 20,
    dry_run: bool = False,
) -> None:
    """Scrape leads for the chosen vertical."""
    if dry_run:
        print(f"[DRY-RUN] Decided to scrape: {vertical} in {location} (n={n})")
        return

    log.info("Scraping %d leads for '%s' in %s ...", n, vertical, location)

    try:
        from vibe_scraper import vibe_scrape

        vibe_scrape(vertical, location, n)
        log.info("Vibe scrape completed for '%s'.", vertical)
    except Exception as e:
        log.warning("vibe_scrape failed: %s — falling back to scraper.py", e)
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(_ROOT / "scripts" / "scraper.py"),
                    f"{vertical} in {location}",
                ],
                check=True,
            )
            log.info("Fallback scraper completed for '%s'.", vertical)
        except Exception as e2:
            log.error("Fallback scraper also failed: %s", e2)
            return

    try:
        brain_client.add(
            f"Scraped {n} leads for {vertical} in {location}",
            category="targeting",
        )
    except Exception as e:
        log.warning("Failed to report to brain: %s", e)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Brain-driven niche targeting agent for BerkahKarya outreach."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what WOULD be scraped without actually calling the scraper.",
    )
    parser.add_argument(
        "--vertical",
        type=str,
        default=None,
        help="Override vertical instead of consulting brain.",
    )
    parser.add_argument(
        "--location",
        type=str,
        default="Jakarta",
        help="Location to scrape (default: Jakarta).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of leads to scrape (default: 20).",
    )
    args = parser.parse_args()

    if args.vertical:
        vertical = args.vertical
        log.info("Using CLI-overridden vertical: %s", vertical)
    else:
        vertical = decide_vertical()

    print(f"Decided to scrape: {vertical}")
    run_scraping(vertical, args.location, args.count, args.dry_run)


if __name__ == "__main__":
    main()
