from pathlib import Path

from oneai_reach.application.outreach.proposal_pdf import (
    MAX_PROPOSAL_PDF_BYTES,
    ProposalPdfError,
    generate_proposal_pdf,
    persist_proposal_pdf,
    proposal_pdf_filename,
    proposal_text_to_html,
)


def test_proposal_text_to_html_escapes_raw_content():
    html = proposal_text_to_html("Hello <script>alert(1)</script>", "ACME & Co")

    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "ACME &amp; Co" in html


def test_generate_proposal_pdf_returns_pdf_bytes():
    pdf = generate_proposal_pdf("Hello team\n\nProposal body", "ACME")

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
    assert len(pdf) <= MAX_PROPOSAL_PDF_BYTES


def test_generate_proposal_pdf_wraps_renderer_failures(monkeypatch):
    class BrokenHTML:
        def __init__(self, string: str):
            self.string = string

        def write_pdf(self):
            raise OSError("missing cairo")

    monkeypatch.setattr("oneai_reach.application.outreach.proposal_pdf.HTML", BrokenHTML)

    try:
        generate_proposal_pdf("Hello", "ACME")
    except ProposalPdfError as exc:
        assert "missing cairo" in str(exc)
    else:
        raise AssertionError("Expected ProposalPdfError")


def test_generate_proposal_pdf_rejects_invalid_pdf(monkeypatch):
    class InvalidHTML:
        def __init__(self, string: str):
            self.string = string

        def write_pdf(self):
            return b"not-a-pdf"

    monkeypatch.setattr("oneai_reach.application.outreach.proposal_pdf.HTML", InvalidHTML)

    try:
        generate_proposal_pdf("Hello", "ACME")
    except ProposalPdfError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("Expected ProposalPdfError")


def test_proposal_pdf_filename_sanitizes_names():
    assert proposal_pdf_filename("ACME / Demo: Jakarta") == "Proposal_ACME_Demo_Jakarta.pdf"
    assert proposal_pdf_filename("!!!") == "Proposal_Business.pdf"


def test_persist_proposal_pdf_writes_sent_pdf(tmp_path: Path):
    draft_dir = tmp_path / "proposals" / "drafts"
    draft_dir.mkdir(parents=True)

    path = persist_proposal_pdf(b"%PDF-test", draft_dir, 7, "ACME / Demo")

    assert path == tmp_path / "proposals" / "sent_pdfs" / "7_Proposal_ACME_Demo.pdf"
    assert path.read_bytes() == b"%PDF-test"
