import asyncio
from email.message import EmailMessage
from urllib.parse import urlencode

import aiosmtplib
import boto3

from backend.mail.config import mail_settings
from backend.mail.service import EmailSender
from backend.mail.templates import render_verification_email


def _confirm_email_url(token: str) -> str:
    query = urlencode({"token": token})
    return f"{mail_settings.API_BASE_URL}/auth/confirm-email?{query}"


class SesEmailSender:
    """Sends verification email via AWS SES."""

    def __init__(self) -> None:
        self._client = boto3.client("ses", region_name=mail_settings.AWS_REGION)

    async def send_verification_email(self, *, email: str, token: str) -> None:
        rendered = render_verification_email(confirm_email_url=_confirm_email_url(token))
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


class SmtpEmailSender:
    """Sends verification email via SMTP (a local catcher such as Mailpit in dev)."""

    async def send_verification_email(self, *, email: str, token: str) -> None:
        rendered = render_verification_email(confirm_email_url=_confirm_email_url(token))

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
