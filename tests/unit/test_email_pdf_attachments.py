from types import SimpleNamespace

import scripts.senders as legacy_senders
from oneai_reach.infrastructure.messaging.email_sender import EmailSender


def test_legacy_send_email_does_not_count_queue_as_sent_with_required_pdf(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(legacy_senders, "EMAIL_QUEUE_LOG", str(tmp_path / "email_queue.log"))
    monkeypatch.setattr(
        legacy_senders,
        "_send_via_brevo",
        lambda *args: calls.append("brevo") and False,
    )
    monkeypatch.setattr(
        legacy_senders,
        "_send_via_stalwart",
        lambda *args: calls.append("stalwart") and False,
    )
    monkeypatch.setattr(
        legacy_senders,
        "_send_via_gog",
        lambda *args: calls.append("gog") and True,
    )
    monkeypatch.setattr(
        legacy_senders,
        "_send_via_himalaya",
        lambda *args: calls.append("himalaya") and True,
    )

    sent = legacy_senders.send_email(
        "lead@example.com",
        "Subject",
        "Body",
        pdf_bytes=b"%PDF-test",
        filename="proposal.pdf",
    )

    assert sent is False
    assert calls == ["brevo", "stalwart"]
    assert (tmp_path / "email_attachments" / "proposal.pdf").read_bytes() == b"%PDF-test"


def test_email_sender_does_not_count_queue_as_sent_with_required_pdf(monkeypatch, tmp_path):
    settings = SimpleNamespace(
        database=SimpleNamespace(logs_dir=str(tmp_path), db_file=str(tmp_path / "leads.db")),
        email=SimpleNamespace(
            brevo_api_key="",
            smtp_from="BerkahKarya <marketing@example.com>",
            smtp_password="",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="marketing@example.com",
        ),
        gmail=SimpleNamespace(keyring_password="secret", account="marketing@example.com"),
    )
    sender = EmailSender(settings, queue_log_path=str(tmp_path / "email_queue.log"))
    calls = []

    monkeypatch.setattr(
        sender,
        "_send_via_brevo",
        lambda *args: calls.append("brevo") and False,
    )
    monkeypatch.setattr(
        sender,
        "_send_via_stalwart",
        lambda *args: calls.append("stalwart") and False,
    )
    monkeypatch.setattr(
        sender,
        "_send_via_gog",
        lambda *args: calls.append("gog") and True,
    )
    monkeypatch.setattr(
        sender,
        "_send_via_himalaya",
        lambda *args: calls.append("himalaya") and True,
    )

    sent = sender.send(
        "lead@example.com",
        "Subject",
        "Body",
        pdf_bytes=b"%PDF-test",
        filename="proposal.pdf",
    )

    assert sent is False
    assert calls == ["brevo", "stalwart"]
    assert (tmp_path / "email_attachments" / "proposal.pdf").read_bytes() == b"%PDF-test"


def test_legacy_send_email_still_allows_queue_without_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(legacy_senders, "EMAIL_QUEUE_LOG", str(tmp_path / "email_queue.log"))
    monkeypatch.setattr(legacy_senders, "_send_via_brevo", lambda *args: False)
    monkeypatch.setattr(legacy_senders, "_send_via_stalwart", lambda *args: False)
    monkeypatch.setattr(legacy_senders, "_send_via_gog", lambda *args: False)
    monkeypatch.setattr(legacy_senders, "_send_via_himalaya", lambda *args: False)

    assert legacy_senders.send_email("lead@example.com", "Subject", "Body") is True
    assert "lead@example.com" in (tmp_path / "email_queue.log").read_text()
