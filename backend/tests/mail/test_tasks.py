"""Celery task wiring for the email outbox.

The dispatch path is a single task (`dispatch_email`); the outbox row's `kind`
decides which template/sender it uses (covered in tests/mail/test_service.py).
The sweep re-dispatches every stale PENDING row through that one task.
"""

from backend.mail import tasks


class TestSweepPendingEmails:
    def test_redispatches_every_stale_entry_through_the_single_task(self, monkeypatch):
        async def fake_sweep() -> list[str]:
            return ["id-1", "id-2", "id-3"]

        dispatched: list[str] = []
        monkeypatch.setattr(tasks, "_sweep_pending_emails", fake_sweep)
        monkeypatch.setattr(tasks.dispatch_email, "delay", dispatched.append)

        tasks.sweep_pending_emails()

        assert dispatched == ["id-1", "id-2", "id-3"]

    def test_no_stale_entries_dispatches_nothing(self, monkeypatch):
        async def fake_sweep() -> list[str]:
            return []

        dispatched: list[str] = []
        monkeypatch.setattr(tasks, "_sweep_pending_emails", fake_sweep)
        monkeypatch.setattr(tasks.dispatch_email, "delay", dispatched.append)

        tasks.sweep_pending_emails()

        assert dispatched == []


class TestTaskRegistration:
    def test_dispatch_email_task_is_registered_under_its_name(self):
        assert "backend.mail.tasks.dispatch_email" in tasks.celery_app.tasks

    def test_the_old_per_kind_task_name_is_gone(self):
        assert "backend.mail.tasks.dispatch_verification_email" not in tasks.celery_app.tasks
        assert "backend.mail.tasks.dispatch_password_reset_email" not in tasks.celery_app.tasks
