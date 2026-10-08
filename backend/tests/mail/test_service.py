import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from backend.mail import service
from backend.mail.exceptions import EmailOutboxEntryNotFound
from backend.mail.models import EmailKind, EmailOutboxStatus
from tests.mail.fakes import (
    FakeEmailSender,
    SentOAuthLinkEmail,
    SentPasswordResetEmail,
    SentVerificationEmail,
)

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


class TestOAuthLinkDispatch:
    async def test_oauth_link_entry_is_dispatched_via_the_oauth_link_sender(
        self, email_outbox_repo, email_sender
    ):
        entry = await service.enqueue_email(
            email_outbox_repo,
            user_id="user-1",
            email="ada@example.com",
            token="link-token",
            created_at=NOW,
            kind=EmailKind.OAUTH_LINK,
        )

        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)

        assert email_sender.sent_oauth_link == [
            SentOAuthLinkEmail(email="ada@example.com", token="link-token")
        ]
        assert email_sender.sent == []
        assert email_sender.sent_password_reset == []


class TestListStalePendingEmails:
    async def _create(self, email_outbox_repo):
        return await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )

    async def _fail_once(self, email_outbox_repo, email_sender, entry, *, at):
        email_sender.fail_with = RuntimeError("timeout")
        with pytest.raises(RuntimeError):
            await service.dispatch_email(
                email_outbox_repo, email_sender, entry.id, now=at, max_attempts=5
            )

    async def _stale(self, email_outbox_repo, *, now):
        return await service.list_stale_pending_emails(
            email_outbox_repo,
            unattempted_before=now - timedelta(minutes=2),
            attempted_before=now - timedelta(minutes=20),
        )

    async def test_never_attempted_entry_is_swept_after_the_short_cutoff(self, email_outbox_repo):
        entry = await self._create(email_outbox_repo)

        stale = await self._stale(email_outbox_repo, now=NOW + timedelta(minutes=3))

        assert [e.id for e in stale] == [entry.id]

    async def test_never_attempted_entry_is_not_swept_before_the_short_cutoff(
        self, email_outbox_repo
    ):
        await self._create(email_outbox_repo)

        stale = await self._stale(email_outbox_repo, now=NOW + timedelta(minutes=1))

        assert stale == []

    async def test_entry_waiting_for_its_next_retry_is_not_swept(
        self, email_outbox_repo, email_sender
    ):
        """The longest retry wait is 16 min; the sweep must not cut it short."""
        entry = await self._create(email_outbox_repo)
        await self._fail_once(email_outbox_repo, email_sender, entry, at=NOW)

        stale = await self._stale(email_outbox_repo, now=NOW + timedelta(minutes=16))

        assert stale == []

    async def test_attempted_entry_idle_past_the_long_cutoff_is_swept(
        self, email_outbox_repo, email_sender
    ):
        entry = await self._create(email_outbox_repo)
        await self._fail_once(email_outbox_repo, email_sender, entry, at=NOW)

        stale = await self._stale(email_outbox_repo, now=NOW + timedelta(minutes=21))

        assert [e.id for e in stale] == [entry.id]

    async def test_attempted_entry_uses_its_last_attempt_not_its_creation_time(
        self, email_outbox_repo, email_sender
    ):
        entry = await self._create(email_outbox_repo)
        last_attempt = NOW + timedelta(hours=1)
        await self._fail_once(email_outbox_repo, email_sender, entry, at=last_attempt)

        stale = await self._stale(email_outbox_repo, now=last_attempt + timedelta(minutes=5))

        assert stale == []

    async def test_excludes_sent_entries(self, email_outbox_repo, email_sender):
        entry = await self._create(email_outbox_repo)
        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)

        stale = await self._stale(email_outbox_repo, now=NOW + timedelta(hours=1))

        assert stale == []

    async def test_excludes_dead_entries(self, email_outbox_repo):
        entry = await self._create(email_outbox_repo)
        await email_outbox_repo.mark_dead(entry.id, failed_at=NOW)

        stale = await self._stale(email_outbox_repo, now=NOW + timedelta(hours=1))

        assert stale == []


class TestConcurrentDispatch:
    """Two workers racing one outbox row must produce one email, not two.

    The worker tier scales freely, so the same `entry_id` can reach two
    processes at once: Celery redelivery, or the sweep re-queueing a row whose
    first dispatch is still in flight.
    """

    async def _entry(self, email_outbox_repo):
        return await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=NOW
        )

    async def test_two_concurrent_dispatches_send_one_email(self, email_outbox_repo):
        gate = asyncio.Event()
        email_sender = FakeEmailSender(gate=gate)
        entry = await self._entry(email_outbox_repo)

        both = asyncio.gather(
            service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW),
            service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW),
        )
        await asyncio.sleep(0)  # let both reach the gate
        gate.set()
        await both

        assert email_sender.sent == [
            SentVerificationEmail(email="ada@example.com", token="raw-token")
        ]

    async def test_the_loser_of_the_race_leaves_the_entry_sent(self, email_outbox_repo):
        gate = asyncio.Event()
        email_sender = FakeEmailSender(gate=gate)
        entry = await self._entry(email_outbox_repo)

        both = asyncio.gather(
            service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW),
            service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW),
        )
        await asyncio.sleep(0)
        gate.set()
        await both

        updated = await email_outbox_repo.get_by_id(entry.id)
        assert updated.status == EmailOutboxStatus.SENT

    async def test_a_claimed_entry_is_not_dispatched_again(self, email_outbox_repo, email_sender):
        entry = await self._entry(email_outbox_repo)
        await email_outbox_repo.claim_for_send(entry.id, now=NOW)

        await service.dispatch_email(email_outbox_repo, email_sender, entry.id, now=NOW)

        assert email_sender.sent == []

    async def test_claiming_moves_the_entry_out_of_pending(self, email_outbox_repo):
        entry = await self._entry(email_outbox_repo)

        claimed = await email_outbox_repo.claim_for_send(entry.id, now=NOW)

        assert claimed is not None
        assert claimed.status == EmailOutboxStatus.SENDING

    async def test_a_second_claim_returns_none(self, email_outbox_repo):
        entry = await self._entry(email_outbox_repo)
        await email_outbox_repo.claim_for_send(entry.id, now=NOW)

        assert await email_outbox_repo.claim_for_send(entry.id, now=NOW) is None

    async def test_a_failed_send_releases_the_claim_for_the_retry(
        self, email_outbox_repo, email_sender
    ):
        entry = await self._entry(email_outbox_repo)
        email_sender.fail_with = RuntimeError("provider timeout")

        with pytest.raises(RuntimeError):
            await service.dispatch_email(
                email_outbox_repo, email_sender, entry.id, now=NOW, max_attempts=3
            )

        updated = await email_outbox_repo.get_by_id(entry.id)
        assert updated.status == EmailOutboxStatus.PENDING


class TestAbandonedClaims:
    """A worker killed mid-send leaves a row `sending` with nobody sending it.

    Scaling the worker tier in makes this routine, so the sweep has to reclaim
    the row, but only well past the point a real send could still be running.
    """

    async def _claimed(self, email_outbox_repo, *, at):
        entry = await email_outbox_repo.create(
            user_id="user-1", email="ada@example.com", token="raw-token", created_at=at
        )
        await email_outbox_repo.claim_for_send(entry.id, now=at)
        return entry

    async def test_a_stale_claim_is_swept(self, email_outbox_repo):
        entry = await self._claimed(email_outbox_repo, at=NOW)

        stale = await service.list_stale_pending_emails(
            email_outbox_repo,
            unattempted_before=NOW - timedelta(minutes=2),
            attempted_before=NOW - timedelta(minutes=20),
            claimed_before=NOW + timedelta(minutes=6),
        )

        assert [e.id for e in stale] == [entry.id]

    async def test_a_fresh_claim_is_left_alone(self, email_outbox_repo):
        await self._claimed(email_outbox_repo, at=NOW)

        stale = await service.list_stale_pending_emails(
            email_outbox_repo,
            unattempted_before=NOW + timedelta(minutes=10),
            attempted_before=NOW + timedelta(minutes=10),
            claimed_before=NOW - timedelta(minutes=1),
        )

        assert stale == []

    async def test_a_stale_claim_can_be_reclaimed_and_sent(self, email_outbox_repo, email_sender):
        entry = await self._claimed(email_outbox_repo, at=NOW)
        later = NOW + timedelta(minutes=10)

        await service.dispatch_email(
            email_outbox_repo,
            email_sender,
            entry.id,
            now=later,
            sending_stale_before=later - timedelta(minutes=5),
        )

        assert email_sender.sent == [
            SentVerificationEmail(email="ada@example.com", token="raw-token")
        ]

    async def test_a_fresh_claim_cannot_be_stolen(self, email_outbox_repo, email_sender):
        entry = await self._claimed(email_outbox_repo, at=NOW)

        await service.dispatch_email(
            email_outbox_repo,
            email_sender,
            entry.id,
            now=NOW + timedelta(seconds=30),
            sending_stale_before=NOW - timedelta(minutes=5),
        )

        assert email_sender.sent == []
