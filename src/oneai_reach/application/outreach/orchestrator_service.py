import json
import subprocess
from datetime import datetime
from pathlib import Path

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.legacy.config import RESEARCH_DIR, PROPOSALS_DIR, LEADS_FILE
from oneai_reach.infrastructure.legacy.leads import load_leads, save_leads
from oneai_reach.infrastructure.legacy import brain_client as brain
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class OrchestratorService:

    def __init__(self, config: Settings):
        self.config = config
        self.scripts_dir = Path(__file__).parent.parent.parent.parent / "scripts"

    def run_gmaps_scraper(self, query: str, max_results: int = 60) -> bool:
        """Scrape leads using gosom Google Maps scraper."""
        logger.info(f"Scraping leads via gosom: {query}")
        try:
            from oneai_reach.infrastructure.legacy.gmaps_client import GmapsScraperClient
            from leads import load_leads, save_leads

            client = GmapsScraperClient()
            results = client.scrape(query, max_results)

            if not results:
                logger.warning("gosom scraper returned no results")
                return False

            df = load_leads()
            existing_websites = set()
            existing_emails = set()
            if df is not None and not df.empty:
                existing_websites = {str(w).strip().lower() for w in df.get("websiteUri", []) if str(w).strip()}
                existing_emails = {str(e).strip().lower() for e in df.get("email", []) if str(e).strip()}

            new_leads = []
            for lead in results:
                website = str(lead.get("websiteUri", "")).strip().lower()
                email = str(lead.get("email", "")).strip().lower()
                if website and website in existing_websites:
                    continue
                if email and email in existing_emails:
                    continue
                lead["status"] = "new"
                lead["source"] = "gmaps_scraper"
                new_leads.append(lead)
                existing_websites.add(website)
                existing_emails.add(email)

            if new_leads:
                import pandas as pd
                new_df = pd.DataFrame(new_leads)
                if df is not None and not df.empty:
                    df = pd.concat([df, new_df], ignore_index=True)
                else:
                    df = new_df
                save_leads(df)
                logger.info(f"Inserted {len(new_leads)} new leads (deduped from {len(results)} results)")
            else:
                logger.info("No new leads to insert (all duplicates)")

            return True
        except Exception as e:
            logger.error(f"gosom scraper error: {e}")
            return False

    def run_service_detection(self) -> bool:
        """Run service_detector on leads that don't have matched_services yet."""
        logger.info("Running service detection on new leads")
        try:
            from oneai_reach.infrastructure.legacy.leads import load_leads, save_leads
            from oneai_reach.infrastructure.legacy.service_detector import detect_services

            df = load_leads()
            if df is None or df.empty:
                return True

            updated = 0
            for idx, row in df.iterrows():
                if row.get("matched_services") and str(row.get("matched_services", "")).strip() not in ("", "nan", "None"):
                    continue

                lead = row.to_dict()
                research_text = str(row.get("research", ""))
                services = detect_services(lead, {"text_sample": research_text})

                if services:
                    service_names = [s["service"] for s in services[:2]]
                    df.at[idx, "matched_services"] = json.dumps(service_names)
                    df.at[idx, "service_proposed"] = service_names[0]
                    updated += 1

            if updated:
                save_leads(df)
                logger.info(f"Detected services for {updated} leads")
            return True
        except Exception as e:
            logger.error(f"Service detection error: {e}")
            return False

    def run_lead_scoring(self) -> bool:
        """Run lead_scorer on leads that don't have a score yet."""
        logger.info("Running lead scoring on new leads")
        try:
            from oneai_reach.infrastructure.legacy.leads import load_leads, save_leads
            from oneai_reach.infrastructure.legacy.lead_scorer import score_lead

            df = load_leads()
            if df is None or df.empty:
                return True

            updated = 0
            for idx, row in df.iterrows():
                try:
                    score = float(row.get("lead_score", 0) or 0)
                except (ValueError, TypeError):
                    score = 0
                if score > 0:
                    continue

                lead = row.to_dict()
                research_text = str(row.get("research", ""))
                result = score_lead(lead, {"text_sample": research_text})

                df.at[idx, "lead_score"] = result["total_score"]
                df.at[idx, "tier"] = result["tier"]
                updated += 1

            if updated:
                save_leads(df)
                logger.info(f"Scored {updated} leads")
            return True
        except Exception as e:
            logger.error(f"Lead scoring error: {e}")
            return False

    def run_full_pipeline(self, query: str, dry_run: bool = False, scraper_source: str = "gmaps", max_leads: int = 60) -> dict:
        industry, _, location_part = query.partition(" in ")
        location = location_part.strip() or "Jakarta, Indonesia"
        industry = industry.strip() or query

        logger.info(f"Starting {'DRY RUN' if dry_run else 'FULL'} pipeline")
        logger.info(f"Industry: {industry}, Location: {location}")

        results = {}

        if scraper_source == "gmaps":
            results["gmaps_scraper"] = self.run_gmaps_scraper(query, max_leads)
        elif scraper_source == "vibe":
            results["vibe_scraper"] = self._run_step("vibe_scraper.py", "Discovering decision-maker leads via Vibe Prospecting", [industry, location, "20"])
        results["scraper"] = self._run_step("scraper.py", "Scraping additional leads via Google Places", [query])

        results["service_detection"] = self.run_service_detection()
        results["lead_scoring"] = self.run_lead_scoring()

        results["enricher"] = self._run_step("enricher.py", "Enriching contact info")
        results["researcher"] = self._run_step("researcher.py", "Researching prospect pain points")
        results["generator"] = self._run_step("generator.py", "Generating personalized proposals")
        results["reviewer"] = self._run_step("reviewer.py", "Reviewing proposal quality")
        results["generator_retry"] = self._run_step("generator.py", "Re-generating weak proposals")

        if not dry_run:
            results["blaster"] = self._run_step("blaster.py", "Sending proposals via email + WhatsApp")

        results["reply_tracker"] = self._run_step("reply_tracker.py", "Checking for replies (Gmail + WAHA)")

        if not dry_run:
            results["converter"] = self._run_step("converter.py", "Converting replies → meeting invites + PaperClip")

        results["followup"] = self._run_step("followup.py", "Sending follow-ups to non-responders")
        results["sheets_sync"] = self._run_step("sheets_sync.py", "Syncing funnel status to Google Sheet")
        results["brain_sync"] = self._brain_sync()

        logger.info("Pipeline complete")
        return results

    def run_followup_only(self) -> dict:
        logger.info("Starting follow-up cycle")
        results = {}
        results["reply_tracker"] = self._run_step("reply_tracker.py", "Checking for replies (Gmail + WAHA)")
        results["converter"] = self._run_step("converter.py", "Converting replies → meeting invites")
        results["followup"] = self._run_step("followup.py", "Sending follow-ups to non-responders")
        results["sheets_sync"] = self._run_step("sheets_sync.py", "Syncing funnel status to Google Sheet")
        results["brain_sync"] = self._brain_sync()
        logger.info("Follow-up cycle complete")
        return results

    def run_enrich_only(self) -> dict:
        logger.info("Starting enrichment cycle")
        results = {}
        results["enricher"] = self._run_step("enricher.py", "Enriching contact info")
        results["researcher"] = self._run_step("researcher.py", "Researching prospect pain points")
        results["sheets_sync"] = self._run_step("sheets_sync.py", "Syncing funnel status to Google Sheet")
        logger.info("Enrichment complete")
        return results

    def run_sync_only(self) -> dict:
        logger.info("Starting sync cycle")
        results = {}
        results["sheets_sync"] = self._run_step("sheets_sync.py", "Syncing funnel status to Google Sheet")
        results["brain_sync"] = self._brain_sync()
        logger.info("Sync complete")
        return results

    def _run_step(self, script: str, label: str, args: list = None) -> bool:
        if args is None:
            args = []
        logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] {label}")
        result = subprocess.run(
            ["python3", str(self.scripts_dir / script)] + args,
            capture_output=False,
        )
        if result.returncode != 0:
            logger.warning(f"{script} exited with code {result.returncode}. Continuing pipeline...")
        return result.returncode == 0

    def _brain_sync(self) -> bool:
        logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] Syncing outcomes to hub brain")
        try:
            if not brain.is_online():
                logger.info("Hub brain offline — skipping brain sync")
                return False

            df = load_leads()
            if df is not None:
                brain.learn_batch_outcomes(df)
                stats = brain.stats()
                if stats:
                    total = stats.get("total", stats.get("file_based_memories", "?"))
                    logger.info(f"[brain] Total memories in hub: {total}")
            return True
        except Exception as e:
            logger.error(f"Brain sync error: {e}")
            return False
