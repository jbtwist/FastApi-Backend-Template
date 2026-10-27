"""Celery task wiring for the email outbox.

The dispatch path is a single task (`dispatch_email`); the outbox row's `kind`
decides which template/sender it uses (covered in tests/mail/test_service.py).
The sweep re-dispatches every stale PENDING row through that one task, unless
the broker queue still holds dispatches.
"""

import uuid
from collections.abc import Callable, Iterator

import pytest
from celery import Celery

from backend.mail import tasks


@pytest.fixture
def broker_queue_depth(monkeypatch) -> Callable[[int], None]:
    """Set what `tasks.broker_queue_depth` reports, instead of asking the real broker."""

    def set_depth(depth: int) -> None:
        monkeypatch.setattr(tasks, "broker_queue_depth", lambda _app: depth)

    return set_depth


@pytest.fixture
def dispatched(monkeypatch) -> list[str]:
    """Entry ids passed to `dispatch_email.delay`, in order."""
    sent: list[str] = []
    monkeypatch.setattr(tasks.dispatch_email, "delay", sent.append)
    return sent


class TestSweepPendingEmails:
    def test_redispatches_every_stale_entry_through_the_single_task(
        self, monkeypatch, broker_queue_depth, dispatched
    ):
        async def fake_sweep() -> list[str]:
            return ["id-1", "id-2", "id-3"]

        broker_queue_depth(0)
        monkeypatch.setattr(tasks, "_sweep_pending_emails", fake_sweep)

        tasks.sweep_pending_emails()

        assert dispatched == ["id-1", "id-2", "id-3"]

    def test_no_stale_entries_dispatches_nothing(self, monkeypatch, broker_queue_depth, dispatched):
        async def fake_sweep() -> list[str]:
            return []

        broker_queue_depth(0)
        monkeypatch.setattr(tasks, "_sweep_pending_emails", fake_sweep)

        tasks.sweep_pending_emails()

        assert dispatched == []

    @pytest.mark.parametrize("depth", [1, 30_000])
    def test_skips_while_dispatches_are_still_waiting_in_the_broker(
        self, monkeypatch, broker_queue_depth, dispatched, depth
    ):
        """A stale row may just be queued behind a backlog; re-queueing it only adds a copy."""
        swept = False

        async def fake_sweep() -> list[str]:
            nonlocal swept
            swept = True
            return ["id-1"]

        broker_queue_depth(depth)
        monkeypatch.setattr(tasks, "_sweep_pending_emails", fake_sweep)

        tasks.sweep_pending_emails()

        assert dispatched == []
        assert swept is False


@pytest.fixture
def memory_celery_app() -> Iterator[Celery]:
    """A Celery app on kombu's in-process memory broker, with a queue of its own."""
    app = Celery("test", broker="memory://")
    app.conf.task_default_queue = f"test-{uuid.uuid4().hex}"
    yield app
    with app.connection_for_write() as conn:
        conn.default_channel.queue_purge(app.conf.task_default_queue)


class TestBrokerQueueDepth:
    def test_an_empty_queue_has_depth_zero(self, memory_celery_app):
        assert tasks.broker_queue_depth(memory_celery_app) == 0

    def test_counts_every_message_waiting_in_the_default_queue(self, memory_celery_app):
        for _ in range(3):
            memory_celery_app.send_task("backend.mail.tasks.dispatch_email", args=["id"])

        assert tasks.broker_queue_depth(memory_celery_app) == 3

    def test_ignores_messages_on_other_queues(self, memory_celery_app):
        other = f"other-{uuid.uuid4().hex}"
        memory_celery_app.send_task("backend.mail.tasks.dispatch_email", args=["id"], queue=other)

        try:
            assert tasks.broker_queue_depth(memory_celery_app) == 0
        finally:
            with memory_celery_app.connection_for_write() as conn:
                conn.default_channel.queue_purge(other)


class TestTaskRegistration:
    def test_dispatch_email_task_is_registered_under_its_name(self):
        assert "backend.mail.tasks.dispatch_email" in tasks.celery_app.tasks

    def test_the_old_per_kind_task_name_is_gone(self):
        assert "backend.mail.tasks.dispatch_verification_email" not in tasks.celery_app.tasks
        assert "backend.mail.tasks.dispatch_password_reset_email" not in tasks.celery_app.tasks


class TestDispatchRetrySchedule:
    def test_waits_double_from_two_minutes_up_to_sixteen_without_jitter(self):
        """With the default five attempts, the waits total 30 min."""
        task = tasks.dispatch_email

        assert task.retry_backoff == 120
        assert task.retry_backoff_max == 960
        assert task.retry_jitter is False

    def test_celery_stops_retrying_when_the_entry_goes_dead(self):
        max_attempts = tasks.mail_settings.EMAIL_MAX_DISPATCH_ATTEMPTS

        assert tasks.dispatch_email.max_retries == max_attempts - 1

    def test_sweep_leaves_entries_alone_for_longer_than_the_longest_retry_wait(self):
        retrying_stale_after = tasks.mail_settings.EMAIL_SWEEP_RETRYING_STALE_AFTER_SECONDS

        assert retrying_stale_after > tasks.dispatch_email.retry_backoff_max


class TestAbandonedClaimRecovery:
    """A worker killed mid-send leaves its row `sending`; the sweep takes it back."""

    def test_an_abandoned_claim_outlives_a_sweep_interval(self):
        """Otherwise a sweep reclaims a row the previous sweep had just handed out."""
        sending_stale_after = tasks.mail_settings.EMAIL_SWEEP_SENDING_STALE_AFTER_SECONDS

        assert sending_stale_after > tasks.mail_settings.EMAIL_SWEEP_INTERVAL_SECONDS

    def test_an_abandoned_claim_is_recovered_sooner_than_a_stalled_retry(self):
        sending_stale_after = tasks.mail_settings.EMAIL_SWEEP_SENDING_STALE_AFTER_SECONDS

        assert sending_stale_after < tasks.mail_settings.EMAIL_SWEEP_RETRYING_STALE_AFTER_SECONDS
