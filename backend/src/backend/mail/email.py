import asyncio
from email.message import EmailMessage
from urllib.parse import urlencode

import aiosmtplib
import boto3

from backend.auth.config import auth_settings
from backend.mail.config import mail_settings
from backend.mail.service import EmailSender
from backend.mail.templates import (
    RenderedEmail,
    humanize_duration,
    render_password_reset_email,
    render_verification_email,
)


def _confirm_email_url(token: str) -> str:
    query = urlencode({"token": token})
    return f"{mail_settings.FRONTEND_BASE_URL}/verify-email-confirm?{query}"


def _reset_password_url(token: str) -> str:
    query = urlencode({"token": token})
    return f"{mail_settings.FRONTEND_BASE_URL}/reset-password?{query}"


class EmailSenderMixin:
    """Shared rendering + link building for every transactional email.

    Providers mix this in and supply `_send` (the transport); the public
    `send_*_email` methods are identical across providers. `EmailSender` (a
    `Protocol` in `mail.service`) stays the structural interface callers depend on.
    """

    async def send_verification_email(self, *, email: str, token: str) -> None:
        rendered = render_verification_email(confirm_email_url=_confirm_email_url(token))
        await self._send(email=email, rendered=rendered)

    async def send_password_reset_email(self, *, email: str, token: str) -> None:
        rendered = render_password_reset_email(
            reset_password_url=_reset_password_url(token),
            expires_in=humanize_duration(auth_settings.PASSWORD_RESET_TOKEN_EXP),
        )
        await self._send(email=email, rendered=rendered)

    async def _send(self, *, email: str, rendered: RenderedEmail) -> None:
        raise NotImplementedError


class SesEmailSender(EmailSenderMixin):
    """Sends transactional email via AWS SES."""

    def __init__(self) -> None:
        self._client = boto3.client("ses", region_name=mail_settings.AWS_REGION)

    async def _send(self, *, email: str, rendered: RenderedEmail) -> None:
        await asyncio.to_thread(
            self._client.send_email,
            Source=mail_settings.FROM_EMAIL,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": rendered.subject},
                "Body": {
                    "Text": {"Data": rendered.text},
                    "Html": {"Data": rendered.html},
                },
            },
        )


class SmtpEmailSender(EmailSenderMixin):
    """Sends transactional email via SMTP (a local catcher such as Mailpit in dev)."""

    async def _send(self, *, email: str, rendered: RenderedEmail) -> None:
        message = EmailMessage()
        message["From"] = mail_settings.FROM_EMAIL
        message["To"] = email
        message["Subject"] = rendered.subject
        message.set_content(rendered.text)
        message.add_alternative(rendered.html, subtype="html")

        await aiosmtplib.send(
            message, hostname=mail_settings.SMTP_HOST, port=mail_settings.SMTP_PORT
        )


def get_email_sender() -> EmailSender:
    if mail_settings.PROVIDER == "ses":
        return SesEmailSender()
    return SmtpEmailSender()
