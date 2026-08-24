import asyncio
from email.message import EmailMessage

import aiosmtplib
import boto3

from backend.mail.config import mail_settings
from backend.mail.service import EmailSender


class SesEmailSender:
    """Sends verification email via AWS SES."""

    def __init__(self) -> None:
        self._client = boto3.client("ses", region_name=mail_settings.AWS_REGION)

    async def send_verification_email(self, *, email: str, token: str) -> None:
        await asyncio.to_thread(
            self._client.send_email,
            Source=mail_settings.FROM_EMAIL,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": "Verify your email"},
                "Body": {"Text": {"Data": f"Verify your email: token={token}"}},
            },
        )


class SmtpEmailSender:
    """Sends verification email via SMTP (a local catcher such as Mailpit in dev)."""

    async def send_verification_email(self, *, email: str, token: str) -> None:
        message = EmailMessage()
        message["From"] = mail_settings.FROM_EMAIL
        message["To"] = email
        message["Subject"] = "Verify your email"
        message.set_content(f"Verify your email: token={token}")

        await aiosmtplib.send(
            message, hostname=mail_settings.SMTP_HOST, port=mail_settings.SMTP_PORT
        )


def get_email_sender() -> EmailSender:
    if mail_settings.PROVIDER == "ses":
        return SesEmailSender()
    return SmtpEmailSender()
