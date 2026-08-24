import logging

logger = logging.getLogger(__name__)


class LoggingEmailSender:
    """Logs the verification link instead of sending real email.

    Placeholder until a real provider (SES, Postmark, etc.) is wired in;
    satisfies the same EmailSender protocol the mail service layer depends on.
    """

    async def send_verification_email(self, *, email: str, token: str) -> None:
        logger.info("verification email for %s: token=%s", email, token)
