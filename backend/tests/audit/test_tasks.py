"""The beat task is a thin wrapper: it opens a session and delegates to the service."""

import pytest

from backend.audit import tasks


class TestSweepSecurityEvents:
    def test_it_delegates_to_the_purge_coroutine(self, monkeypatch):
        calls: list[int] = []

        async def fake_purge() -> int:
            calls.append(1)
            return 7

        monkeypatch.setattr(tasks, "_sweep_security_events", fake_purge)

        tasks.sweep_security_events()

        assert calls == [1]

    def test_it_survives_an_empty_table(self, monkeypatch):
        async def fake_purge() -> int:
            return 0

        monkeypatch.setattr(tasks, "_sweep_security_events", fake_purge)

        tasks.sweep_security_events()


class TestSweepLoop:
    @staticmethod
    def _batches(monkeypatch, sizes: list[int]) -> list[int]:
        """Stub one committed batch per call, returning each size in turn."""
        calls: list[int] = []
        remaining = list(sizes)

        async def fake_batch() -> int:
            calls.append(1)
            return remaining.pop(0) if remaining else 0

        monkeypatch.setattr(tasks, "_purge_one_batch", fake_batch)
        return calls

    @pytest.mark.asyncio
    async def test_it_keeps_going_until_a_batch_comes_back_empty(self, monkeypatch):
        calls = self._batches(monkeypatch, [5000, 5000, 137])

        assert await tasks._sweep_security_events() == 10137
        assert len(calls) == 4

    @pytest.mark.asyncio
    async def test_a_single_partial_batch_ends_the_sweep(self, monkeypatch):
        calls = self._batches(monkeypatch, [12])

        assert await tasks._sweep_security_events() == 12
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_nothing_expired_is_one_query_and_no_deletions(self, monkeypatch):
        calls = self._batches(monkeypatch, [])

        assert await tasks._sweep_security_events() == 0
        assert len(calls) == 1


def test_the_sweep_is_on_the_beat_schedule():
    from backend.mail.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "sweep-security-events" in schedule
    assert schedule["sweep-security-events"]["task"] == "backend.audit.tasks.sweep_security_events"
