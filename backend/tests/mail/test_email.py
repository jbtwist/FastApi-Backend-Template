from email.message import EmailMessage

import pytest

from backend.mail import email as email_module
from backend.mail.config import mail_settings
from backend.mail.email import SesEmailSender, SmtpEmailSender


@pytest.fixture(autouse=True)
def _frontend_url(monkeypatch):
    monkeypatch.setattr(mail_settings, "API_BASE_URL", "https://api.todoapp.local")
    monkeypatch.setattr(mail_settings, "FRONTEND_BASE_URL", "https://app.todoapp.local")
    monkeypatch.setattr(mail_settings, "FROM_EMAIL", "no-reply@todoapp.local")


class TestSmtpEmailSender:
    async def test_sends_a_multipart_message_with_a_confirm_link(self, monkeypatch):
        sent: list[EmailMessage] = []

        async def fake_send(message, *, hostname, port):
            sent.append(message)

        monkeypatch.setattr(email_module.aiosmtplib, "send", fake_send)

        await SmtpEmailSender().send_verification_email(email="ada@example.com", token="raw-token")

        assert len(sent) == 1
        message = sent[0]
        assert message["From"] == "no-reply@todoapp.local"
        assert message["To"] == "ada@example.com"

        confirm_url = "https://app.todoapp.local/verify-email-confirm?token=raw-token"
        text_body = message.get_body(preferencelist=("plain",)).get_content()
        html_body = message.get_body(preferencelist=("html",)).get_content()
        assert confirm_url in text_body
        assert confirm_url in html_body
        assert "api.todoapp.local" not in text_body
        assert "api.todoapp.local" not in html_body

    async def test_sends_an_oauth_link_email_pointing_at_the_link_confirm_screen(self, monkeypatch):
        sent: list[EmailMessage] = []

        async def fake_send(message, *, hostname, port):
            sent.append(message)

        monkeypatch.setattr(email_module.aiosmtplib, "send", fake_send)

        await SmtpEmailSender().send_oauth_link_email(email="ada@example.com", token="raw-token")

        confirm_url = "https://app.todoapp.local/link-provider-confirm?token=raw-token"
        assert sent[0]["To"] == "ada@example.com"
        assert confirm_url in sent[0].get_body(preferencelist=("plain",)).get_content()
        assert confirm_url in sent[0].get_body(preferencelist=("html",)).get_content()


class TestSesEmailSender:
    async def test_sends_an_email_with_text_and_html_bodies_containing_the_confirm_link(
        self, monkeypatch
    ):
        calls = []

        class FakeSesClient:
            def send_email(self, **kwargs):
                calls.append(kwargs)

        monkeypatch.setattr(email_module.boto3, "client", lambda *a, **kw: FakeSesClient())

        await SesEmailSender().send_verification_email(email="ada@example.com", token="raw-token")

        assert len(calls) == 1
        call = calls[0]
        confirm_url = "https://app.todoapp.local/verify-email-confirm?token=raw-token"
        assert call["Source"] == "no-reply@todoapp.local"
        assert call["Destination"] == {"ToAddresses": ["ada@example.com"]}
        assert confirm_url in call["Message"]["Body"]["Text"]["Data"]
        assert confirm_url in call["Message"]["Body"]["Html"]["Data"]
        assert "api.todoapp.local" not in call["Message"]["Body"]["Text"]["Data"]
        assert "api.todoapp.local" not in call["Message"]["Body"]["Html"]["Data"]
