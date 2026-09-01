from datetime import UTC, datetime, timedelta

import pytest

from backend.mail import service
from backend.mail.exceptions import EmailOutboxEntryNotFound
from backend.mail.models import EmailKind, EmailOutboxStatus
from tests.mail.fakes import SentPasswordResetEmail, SentVerificationEmail

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class TestDispatchEmail:
    async def test_sends_email_and_marks_entry_sent_on_success(
        self, email_outbox_repo, email_sender
    ):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )

        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)

        updated = await email_outbox_repo.get_by_id(entry.id)
        assert updated.status == EmailOutboxStatus.SENT
        assert email_sender.sent == [
            SentVerificationEmail(email="ada@example.com", token="raw-token")
        ]

    async def test_raises_for_an_unknown_outbox_entry(self, email_outbox_repo, email_sender):
        with pytest.raises(EmailOutboxEntryNotFound):
            await service.dispatch_email(email_outbox_repo, email_sender, "does-not-exist", now=NOW)

    async def test_reprocessing_an_already_sent_entry_is_a_noop(
        self, email_outbox_repo, email_sender
    ):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)
        email_sender.sent.clear()

        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)

        assert email_sender.sent == []

    async def test_reprocessing_a_dead_entry_is_a_noop(self, email_outbox_repo, email_sender):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        await email_outbox_repo.mark_dead(entry.id, failed_at=NOW)

        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)

        assert email_sender.sent == []

    async def test_failure_below_max_attempts_stays_pending_and_reraises(
        self, email_outbox_repo, email_sender
    ):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        email_sender.fail_with = RuntimeError("provider timeout")

        with pytest.raises(RuntimeError, match="provider timeout"):
            await service.dispatch_email(
                email_outbox_repo, email_sender, entry.id, now=NOW, max_attempts=3
            )

        updated = await email_outbox_repo.get_by_id(entry.id)
        assert updated.status == EmailOutboxStatus.PENDING
        assert updated.attempts == 1

    async def test_failure_reaching_max_attempts_marks_entry_dead(
        self, email_outbox_repo, email_sender
    ):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        email_sender.fail_with = RuntimeError("provider timeout")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await service.dispatch_email(
                    email_outbox_repo, email_sender, entry.id, now=NOW, max_attempts=2
                )

        updated = await email_outbox_repo.get_by_id(entry.id)
        assert updated.status == EmailOutboxStatus.DEAD
        assert updated.attempts == 2

    async def test_dead_entries_are_never_retried_again(self, email_outbox_repo, email_sender):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        email_sender.fail_with = RuntimeError("provider timeout")
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await service.dispatch_email(
                    email_outbox_repo, email_sender, entry.id, now=NOW, max_attempts=2
                )

        email_sender.fail_with = None  # provider recovers, shouldn't matter anymore
        await service.dispatch_email(
            email_outbox_repo, email_sender, entry.id, now=NOW, max_attempts=2
        )

        assert email_sender.sent == []
        updated = await email_outbox_repo.get_by_id(entry.id)
        assert updated.status == EmailOutboxStatus.DEAD
        assert updated.attempts == 2


class TestEnqueueAndDispatchByKind:
    async def test_enqueue_defaults_to_verification_kind(self, email_outbox_repo):
        entry = await service.enqueue_email(
            email_outbox_repo,
            user_id="user-1",
            email="ada@example.com",
            token="raw-token",
            created_at=NOW,
        )

        assert entry.kind == EmailKind.VERIFICATION

    async def test_password_reset_entry_is_dispatched_via_reset_sender(
        self, email_outbox_repo, email_sender
    ):
        entry = await service.enqueue_email(
            email_outbox_repo,
            user_id="user-1",
            email="ada@example.com",
            token="reset-token",
            created_at=NOW,
            kind=EmailKind.PASSWORD_RESET,
        )

        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)

        assert email_sender.sent == []
        assert email_sender.sent_password_reset == [
            SentPasswordResetEmail(email="ada@example.com", token="reset-token")
        ]
        updated = await email_outbox_repo.get_by_id(entry.id)
        assert updated.status == EmailOutboxStatus.SENT

    async def test_verification_entry_still_uses_the_verification_sender(
        self, email_outbox_repo, email_sender
    ):
        entry = await service.enqueue_email(
            email_outbox_repo,
            user_id="user-1",
            email="ada@example.com",
            token="verify-token",
            created_at=NOW,
        )

        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)

        assert email_sender.sent == [
            SentVerificationEmail(email="ada@example.com", token="verify-token")
        ]
        assert email_sender.sent_password_reset == []


class TestListStalePendingEmails:
    async def test_returns_pending_entries_older_than_cutoff(self, email_outbox_repo):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        cutoff = NOW + timedelta(minutes=2)
        stale = await service.list_stale_pending_emails(email_outbox_repo, older_than=cutoff)

        assert [e.id for e in stale] == [entry.id]

    async def test_excludes_entries_not_yet_stale(self, email_outbox_repo):
        await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        cutoff = NOW - timedelta(minutes=1)
        stale = await service.list_stale_pending_emails(email_outbox_repo, older_than=cutoff)

        assert stale == []

    async def test_excludes_sent_entries(self, email_outbox_repo, email_sender):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)
        cutoff = NOW + timedelta(minutes=2)
        stale = await service.list_stale_pending_emails(email_outbox_repo, older_than=cutoff)

        assert stale == []

    async def test_excludes_dead_entries(self, email_outbox_repo):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        await email_outbox_repo.mark_dead(entry.id, failed_at=NOW)
        cutoff = NOW + timedelta(minutes=2)
        stale = await service.list_stale_pending_emails(email_outbox_repo, older_than=cutoff)

        assert stale == []

    async def test_a_recent_retry_attempt_keeps_it_off_the_sweep(
        self, email_outbox_repo, email_sender
    ):
        """A recent retry must not also be swept."""
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )
        email_sender.fail_with = RuntimeError("timeout")
        recent_attempt = NOW + timedelta(minutes=5)
        with pytest.raises(RuntimeError):
            await service.dispatch_email(
                email_outbox_repo, email_sender, entry.id, now=recent_attempt, max_attempts=5
            )
        cutoff = recent_attempt - timedelta(seconds=30)
        stale = await service.list_stale_pending_emails(email_outbox_repo, older_than=cutoff)

        assert stale == []
