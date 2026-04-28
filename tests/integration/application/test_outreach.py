"""Integration tests for outreach application services."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests

from oneai_reach.application.outreach.blaster_service import BlasterService
from oneai_reach.application.outreach.scraper_service import ScraperService
from oneai_reach.domain.exceptions import ExternalAPIError, MissingConfigurationError


@pytest.fixture
def mock_requests_get():
    with patch("requests.get") as mock:
        yield mock


@pytest.fixture
def mock_requests_post():
    with patch("requests.post") as mock:
        yield mock


class TestScraperService:
    def test_search_google_places_success(self, settings, mock_requests_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "places": [
                {
                    "id": "place_123",
                    "displayName": {"text": "Test Coffee Shop"},
                    "formattedAddress": "Jl. Test No. 1, Jakarta",
                    "internationalPhoneNumber": "+62 21 1234567",
                    "nationalPhoneNumber": "021-1234567",
                    "websiteUri": "https://testcoffee.com",
                    "primaryType": "cafe",
                    "primaryTypeDisplayName": {"text": "Cafe"},
                }
            ]
        }
        mock_requests_post.return_value = mock_response

        service = ScraperService(settings)
        results = service._search_google_places("Coffee Shop in Jakarta")

        assert len(results) == 1
        assert results[0]["displayName"] == "Test Coffee Shop"
        assert results[0]["source"] == "google_places"
        assert results[0]["phone"] == "021-1234567"

    def test_search_google_places_missing_api_key(self, settings):
        settings.external_api.google_api_key = None
        service = ScraperService(settings)

        with pytest.raises(MissingConfigurationError) as exc_info:
            service._search_google_places("Coffee Shop")

        assert "GOOGLE_API_KEY" in str(exc_info.value)

    def test_search_google_places_api_error(self, settings, mock_requests_post):
        mock_requests_post.side_effect = requests.RequestException("API Error")

        service = ScraperService(settings)

        with pytest.raises(ExternalAPIError) as exc_info:
            service._search_google_places("Coffee Shop")

        assert exc_info.value.service == "google_places"

    def test_search_yellowpages_success(self, settings, mock_requests_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <article class="listing">
                <h2>Test Business</h2>
                <div class="phone">021-9876543</div>
                <div class="address">Jl. Yellow No. 2</div>
                <a href="https://testbiz.com" class="website">Website</a>
            </article>
        </html>
        """
        mock_requests_get.return_value = mock_response

        service = ScraperService(settings)
        results = service._search_yellowpages("Restaurant", "jakarta")

        assert len(results) == 1
        assert results[0]["displayName"] == "Test Business"
        assert results[0]["source"] == "yellowpages_id"
        assert results[0]["phone"] == "021-9876543"

    def test_search_duckduckgo_success(self, settings, mock_requests_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <div class="result">
                <h2 class="result__title">Real Business</h2>
                <a class="result__url">realbusiness.com</a>
            </div>
        </html>
        """
        mock_requests_get.return_value = mock_response

        service = ScraperService(settings)
        results = service._search_duckduckgo("Coffee Shop Jakarta")

        assert len(results) == 1
        assert results[0]["displayName"] == "Real Business"
        assert results[0]["websiteUri"] == "https://realbusiness.com"

    def test_search_leads_fallback_chain(
        self, settings, mock_requests_post, mock_requests_get
    ):
        mock_requests_post.side_effect = requests.RequestException("API down")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <article class="listing">
                <h2>Fallback Business</h2>
            </article>
        </html>
        """
        mock_requests_get.return_value = mock_response

        service = ScraperService(settings)
        results = service.search_leads("Coffee Shop", "Jakarta")

        assert len(results) == 1
        assert results[0]["displayName"] == "Fallback Business"

    def test_is_real_business_filters_aggregators(self, settings):
        service = ScraperService(settings)

        assert service._is_real_business("https://realbusiness.com") is True
        assert service._is_real_business("https://google.com") is False
        assert service._is_real_business("https://bing.com") is False
        assert service._is_real_business("") is False


class TestBlasterService:
    def test_blast_proposals_generates_sends_and_persists_pdf(self, settings, tmp_path):
        draft_dir = tmp_path / "proposals" / "drafts"
        draft_dir.mkdir(parents=True)
        settings.database.proposals_dir = str(draft_dir)
        draft_path = draft_dir / "0_ACME.txt"
        draft_path.write_text(
            "---PROPOSAL---\nHello <b>ACME</b>\n---WHATSAPP---\nHalo ACME",
            encoding="utf-8",
        )
        sent_payload = {}

        def send_email(email, subject, body, pdf_bytes=None, filename=None, lead_id=None):
            sent_payload["email"] = email
            sent_payload["subject"] = subject
            sent_payload["body"] = body
            sent_payload["pdf_bytes"] = pdf_bytes
            sent_payload["filename"] = filename
            return True

        df = pd.DataFrame(
            [
                {
                    "displayName": "ACME",
                    "status": "reviewed",
                    "email": "lead@example.com",
                    "phone": "",
                    "contacted_at": "",
                }
            ]
        )

        sent, skipped_cooldown, skipped_no_draft = BlasterService(settings).blast_proposals(
            df,
            send_email,
            lambda phone, message: False,
            lambda index, name: str(draft_path),
            lambda value: value is None or str(value).strip().lower() in {"", "nan", "none"},
            str,
        )

        assert (sent, skipped_cooldown, skipped_no_draft) == (1, 0, 0)
        assert df.at[0, "status"] == "contacted"
        assert sent_payload["pdf_bytes"].startswith(b"%PDF")
        assert sent_payload["filename"] == "Proposal_ACME.pdf"
        assert (tmp_path / "proposals" / "sent_pdfs" / "0_Proposal_ACME.pdf").exists()

    def test_blast_proposals_sends_without_attachment_when_pdf_fails(self, settings, tmp_path, monkeypatch):
        draft_dir = tmp_path / "proposals" / "drafts"
        draft_dir.mkdir(parents=True)
        settings.database.proposals_dir = str(draft_dir)
        draft_path = draft_dir / "0_ACME.txt"
        draft_path.write_text(
            "---PROPOSAL---\nHello ACME\n---WHATSAPP---\n",
            encoding="utf-8",
        )

        def fail_pdf(proposal, lead_name):
            from oneai_reach.application.outreach.proposal_pdf import ProposalPdfError

            raise ProposalPdfError("missing cairo")

        monkeypatch.setattr(
            "oneai_reach.application.outreach.blaster_service.generate_proposal_pdf",
            fail_pdf,
        )

        df = pd.DataFrame(
            [
                {
                    "displayName": "ACME",
                    "status": "reviewed",
                    "email": "lead@example.com",
                    "phone": "",
                    "contacted_at": "",
                }
            ]
        )

        sent, skipped_cooldown, skipped_no_draft = BlasterService(settings).blast_proposals(
            df,
            lambda *args, **kwargs: True,
            lambda phone, message: False,
            lambda index, name: str(draft_path),
            lambda value: value is None or str(value).strip().lower() in {"", "nan", "none"},
            str,
        )

        assert (sent, skipped_cooldown, skipped_no_draft) == (1, 0, 0)
        assert df.at[0, "status"] == "contacted"
