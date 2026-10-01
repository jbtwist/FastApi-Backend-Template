import uuid
from dataclasses import dataclass
from datetime import datetime

from backend.mail.models import EmailKind, EmailOutboxEntry, EmailOutboxStatus


@dataclass
class SentVerificationEmail:
    email: str
    token: str


@dataclass
class SentPasswordResetEmail:
    email: str
    token: str


@dataclass
class SentOAuthLinkEmail:
    email: str
    token: str


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[SentVerificationEmail] = []
        self.sent_password_reset: list[SentPasswordResetEmail] = []
        self.sent_oauth_link: list[SentOAuthLinkEmail] = []
        self.fail_with: Exception | None = None

    async def send_verification_email(self, *, email: str, token: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(SentVerificationEmail(email=email, token=token))

    async def send_password_reset_email(self, *, email: str, token: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent_password_reset.append(SentPasswordResetEmail(email=email, token=token))

    async def send_oauth_link_email(self, *, email: str, token: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent_oauth_link.append(SentOAuthLinkEmail(email=email, token=token))


class FakeEmailOutboxRepository:
    def __init__(self) -> None:
        self._entries_by_id: dict[uuid.UUID, EmailOutboxEntry] = {}

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        token: str,
        created_at: datetime,
        kind: EmailKind = EmailKind.VERIFICATION,
    ) -> EmailOutboxEntry:
        entry = EmailOutboxEntry(
            id=uuid.uuid4(),
            user_id=user_id,
            email=email,
            token=token,
            kind=kind,
            status=EmailOutboxStatus.PENDING,
            attempts=0,
            created_at=created_at,
        )
        self._entries_by_id[entry.id] = entry
        return entry

    async def get_by_id(self, entry_id: uuid.UUID) -> EmailOutboxEntry | None:
        return self._entries_by_id.get(entry_id)

    async def mark_sent(self, entry_id: uuid.UUID, *, sent_at: datetime) -> bool:
        entry = self._entries_by_id.get(entry_id)
        if entry is None or entry.status != EmailOutboxStatus.PENDING:
            return False
        entry.status = EmailOutboxStatus.SENT
        entry.sent_at = sent_at
        return True

    async def mark_attempt_failed(
        self, entry_id: uuid.UUID, *, attempted_at: datetime
    ) -> EmailOutboxEntry:
        entry = self._entries_by_id[entry_id]
        entry.attempts += 1
        entry.last_attempted_at = attempted_at
        return entry

    async def mark_dead(self, entry_id: uuid.UUID, *, failed_at: datetime) -> bool:
        entry = self._entries_by_id.get(entry_id)
        if entry is None:
            return False
        entry.status = EmailOutboxStatus.DEAD
        entry.dead_at = failed_at
        return True

    async def list_stale_pending(
        self, *, unattempted_before: datetime, attempted_before: datetime
    ) -> list[EmailOutboxEntry]:
        return [
            entry
            for entry in self._entries_by_id.values()
            if entry.status == EmailOutboxStatus.PENDING
            and (
                entry.created_at <= unattempted_before
                if entry.attempts == 0
                else entry.last_attempted_at <= attempted_before
            )
        ]
