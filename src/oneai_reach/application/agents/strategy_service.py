"""Brain-driven niche targeting service.

Queries the BerkahKarya hub brain for outreach win data to decide which
vertical converts best, then invokes the scraper for that vertical.

Falls back to a simple rotation through DEFAULT_VERTICALS when the brain
is offline or returns no actionable data.
"""

import json
import subprocess
import sys
from pathlib import Path

# Add scripts directory to path for external client imports
_scripts_dir = Path(__file__).parent.parent.parent.parent.parent / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import brain_client

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class StrategyService:
    """Service for brain-driven vertical targeting and lead scraping."""

    def __init__(self, config: Settings):
        """Initialize strategy service.

        Args:
            config: Application settings
        """
        self.config = config
        self.default_verticals = config.scraper.default_verticals
        self.rotation_file = Path(".sisyphus/strategy_rotation.json")

    def _load_rotation_index(self) -> int:
        """Load the last rotation index from disk, or 0 if missing."""
        try:
            data = json.loads(self.rotation_file.read_text())
            return int(data.get("index", 0))
        except Exception:
            return 0

    def _save_rotation_index(self, index: int) -> None:
        """Persist the current rotation index."""
        self.rotation_file.parent.mkdir(parents=True, exist_ok=True)
        self.rotation_file.write_text(json.dumps({"index": index}))

    def next_from_rotation(self) -> str:
        """Pick the next vertical from DEFAULT_VERTICALS via round-robin.

        Returns:
            Vertical name from rotation
        """
        idx = self._load_rotation_index()
        vertical = self.default_verticals[idx % len(self.default_verticals)]
        self._save_rotation_index((idx + 1) % len(self.default_verticals))
        return vertical

    def _extract_vertical_from_brain(self, text: str) -> str | None:
        """Try to extract a vertical name from brain strategy text.

        Looks for mentions of DEFAULT_VERTICALS (case-insensitive) in the text
        and returns the one that appears most frequently, indicating it converts best.

        Args:
            text: Brain response text

        Returns:
            Vertical name if found, None otherwise
        """
        if not text:
            return None

        text_lower = text.lower()
        counts: dict[str, int] = {}
        for v in self.default_verticals:
            n = text_lower.count(v.lower())
            if n > 0:
                counts[v] = n

        if not counts:
            return None

        return max(counts, key=counts.get)  # type: ignore[arg-type]

    def decide_vertical(self) -> str:
        """Query brain for best-converting vertical or fall back to rotation.

        1. Query brain for 'outreach_win' data to find best-converting vertical.
        2. Parse response to extract the vertical name.
        3. Fall back to rotation if brain is offline or unparseable.

        Returns:
            Vertical name to scrape

        Raises:
            ExternalAPIError: If brain query fails critically (logged as warning)
        """
        try:
            results = brain_client.search(
                "outreach_win best converting vertical", limit=5
            )
            if results:
                combined = " ".join(r.get("content", "") for r in results)
                found = self._extract_vertical_from_brain(combined)
                if found:
                    logger.info(f"Brain recommends vertical: {found} (from win data)")
                    return found

            strategy = brain_client.get_strategy("outreach")
            if strategy:
                found = self._extract_vertical_from_brain(strategy)
                if found:
                    logger.info(f"Brain recommends vertical: {found} (from strategy)")
                    return found

            logger.info("Brain returned no actionable vertical data, using rotation.")
        except Exception as e:
            logger.warning(f"Brain query failed: {e} — using rotation fallback.")

        vertical = self.next_from_rotation()
        logger.info(f"Rotation fallback selected: {vertical}")
        return vertical

    def run_scraping(
        self,
        vertical: str,
        location: str = "Jakarta",
        n: int = 20,
        dry_run: bool = False,
    ) -> None:
        """Scrape leads for the chosen vertical.

        Args:
            vertical: Vertical/niche to scrape
            location: City/location for scraping
            n: Number of leads to scrape
            dry_run: If True, only print what would be scraped

        Raises:
            ExternalAPIError: If both vibe_scraper and fallback scraper fail
        """
        if dry_run:
            logger.info(
                f"[DRY-RUN] Decided to scrape: {vertical} in {location} (n={n})"
            )
            return

        logger.info(f"Scraping {n} leads for '{vertical}' in {location} ...")

        try:
            from vibe_scraper import vibe_scrape

            vibe_scrape(vertical, location, n)
            logger.info(f"Vibe scrape completed for '{vertical}'.")
        except Exception as e:
            logger.warning(f"vibe_scrape failed: {e} — falling back to scraper.py")
            try:
                scripts_dir = Path(__file__).resolve().parents[3] / "scripts"
                subprocess.run(
                    [
                        sys.executable,
                        str(scripts_dir / "scraper.py"),
                        f"{vertical} in {location}",
                    ],
                    check=True,
                )
                logger.info(f"Fallback scraper completed for '{vertical}'.")
            except Exception as e2:
                logger.error(f"Fallback scraper also failed: {e2}")
                raise ExternalAPIError(
                    service="scraper",
                    endpoint="/scrape",
                    status_code=0,
                    reason=f"Both vibe_scraper and fallback scraper failed: {e2}",
                )

        try:
            brain_client.add(
                f"Scraped {n} leads for {vertical} in {location}",
                category="targeting",
            )
        except Exception as e:
            logger.warning(f"Failed to report to brain: {e}")
