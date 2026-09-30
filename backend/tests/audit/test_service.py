"""Tests for recording and purging security events.

These run on the in-memory fake repository. The real SQL behind the Protocol is
covered in `tests/audit/test_repository.py`.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from backend.audit import service
from backend.audit.models import SecurityEventKind
from backend.log import SCRUBBED, correlation_id

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


@pytest.fixture
def audit_records() -> list[logging.LogRecord]:
    """Records the audit logger saw, so the dual write to stdout can be asserted."""
    collected: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            collected.append(record)

    audit_logger = logging.getLogger("backend.audit")
    handler = _Collector()
    audit_logger.addHandler(handler)
    previous = audit_logger.level
    audit_logger.setLevel(logging.DEBUG)
    try:
        yield collected
    finally:
        audit_logger.removeHandler(handler)
        audit_logger.setLevel(previous)


class TestRecordSecurityEvent:
    async def test_writes_a_row_carrying_the_kind_and_user(self, security_event_repo):
        user_id = uuid.uuid4()
        await service.record_security_event(
            security_event_repo,
            SecurityEventKind.LOGIN_SUCCEEDED,
            user_id=user_id,
            occurred_at=NOW,
        )
        [event] = security_event_repo.events
        assert event.kind == SecurityEventKind.LOGIN_SUCCEEDED
        assert event.user_id == user_id
        assert event.occurred_at == NOW

    async def test_returns_the_written_row(self, security_event_repo):
        event = await service.record_security_event(
            security_event_repo, SecurityEventKind.USER_REGISTERED, occurred_at=NOW
        )
        assert event is security_event_repo.events[0]

    async def test_an_event_without_a_user_is_allowed(self, security_event_repo):
        """`login.failed` for an unknown address has no user to attribute it to."""
        await service.record_security_event(
            security_event_repo,
            SecurityEventKind.LOGIN_FAILED,
            occurred_at=NOW,
            reason="invalid_credentials",
        )
        assert security_event_repo.events[0].user_id is None

    async def test_extra_fields_are_stored_as_structured_data(self, security_event_repo):
        await service.record_security_event(
            security_event_repo,
            SecurityEventKind.TOKEN_REUSE_DETECTED,
            occurred_at=NOW,
            reason="spent_token_replayed",
            family_id="fam-1",
        )
        assert security_event_repo.events[0].fields == {
            "reason": "spent_token_replayed",
            "family_id": "fam-1",
        }

    async def test_fields_are_json_safe(self, security_event_repo):
        """The column is JSONB, so a UUID has to reach it as a string, not an object."""
        family_id = uuid.uuid4()
        await service.record_security_event(
            security_event_repo,
            SecurityEventKind.TOKEN_FAMILY_REVOKED,
            occurred_at=NOW,
            family_id=family_id,
        )
        assert security_event_repo.events[0].fields == {"family_id": str(family_id)}

    @pytest.mark.parametrize("field", ["password", "token", "token_hash", "email"])
    async def test_sensitive_fields_are_scrubbed_before_they_reach_the_row(
        self, security_event_repo, field
    ):
        """A durable table is a worse place to leak a secret than a log with retention."""
        await service.record_security_event(
            security_event_repo,
            SecurityEventKind.LOGIN_FAILED,
            occurred_at=NOW,
            **{field: "super-secret-value"},
        )
        assert security_event_repo.events[0].fields[field] == SCRUBBED

    async def test_the_active_correlation_id_is_stamped_on_the_row(self, security_event_repo):
        token = correlation_id.set("req-abc")
        try:
            await service.record_security_event(
                security_event_repo, SecurityEventKind.USER_REGISTERED, occurred_at=NOW
            )
        finally:
            correlation_id.reset(token)
        assert security_event_repo.events[0].correlation_id == "req-abc"

    async def test_correlation_id_is_none_outside_a_request(self, security_event_repo):
        await service.record_security_event(
            security_event_repo, SecurityEventKind.USER_REGISTERED, occurred_at=NOW
        )
        assert security_event_repo.events[0].correlation_id is None

    async def test_it_also_emits_the_audit_event_to_stdout(
        self, security_event_repo, audit_records
    ):
        """One call feeds both sinks, so a call site cannot write the row and forget the log."""
        user_id = uuid.uuid4()
        await service.record_security_event(
            security_event_repo,
            SecurityEventKind.LOGIN_SUCCEEDED,
            user_id=user_id,
            occurred_at=NOW,
        )
        [record] = audit_records
        assert record.event == "login.succeeded"
        assert record.audit_fields["user_id"] == str(user_id)

    async def test_reuse_detection_is_logged_at_warning(self, security_event_repo, audit_records):
        await service.record_security_event(
            security_event_repo, SecurityEventKind.TOKEN_REUSE_DETECTED, occurred_at=NOW
        )
        assert audit_records[0].levelno == logging.WARNING

    async def test_an_ordinary_event_is_logged_at_info(self, security_event_repo, audit_records):
        await service.record_security_event(
            security_event_repo, SecurityEventKind.LOGIN_SUCCEEDED, occurred_at=NOW
        )
        assert audit_records[0].levelno == logging.INFO


class TestPurgeExpiredSecurityEvents:
    async def _seed(self, repo, *ages: timedelta) -> None:
        for age in ages:
            await repo.record(
                kind=SecurityEventKind.LOGIN_SUCCEEDED,
                user_id=None,
                correlation_id=None,
                fields={},
                occurred_at=NOW - age,
            )

    async def test_rows_past_retention_are_deleted(self, security_event_repo):
        await self._seed(security_event_repo, timedelta(days=200))
        deleted = await service.purge_expired_security_events(
            security_event_repo, now=NOW, retention=timedelta(days=180), batch_size=5000
        )
        assert deleted == 1
        assert security_event_repo.events == []

    async def test_rows_inside_retention_are_kept(self, security_event_repo):
        await self._seed(security_event_repo, timedelta(days=1), timedelta(days=179))
        deleted = await service.purge_expired_security_events(
            security_event_repo, now=NOW, retention=timedelta(days=180), batch_size=5000
        )
        assert deleted == 0
        assert len(security_event_repo.events) == 2

    async def test_the_boundary_row_is_kept(self, security_event_repo):
        await self._seed(security_event_repo, timedelta(days=180))
        deleted = await service.purge_expired_security_events(
            security_event_repo, now=NOW, retention=timedelta(days=180), batch_size=5000
        )
        assert deleted == 0

    async def test_it_reports_how_many_it_deleted(self, security_event_repo):
        await self._seed(
            security_event_repo, timedelta(days=400), timedelta(days=300), timedelta(days=1)
        )
        deleted = await service.purge_expired_security_events(
            security_event_repo, now=NOW, retention=timedelta(days=180), batch_size=5000
        )
        assert deleted == 2
        assert len(security_event_repo.events) == 1

    async def test_an_empty_table_purges_nothing(self, security_event_repo):
        assert (
            await service.purge_expired_security_events(
                security_event_repo, now=NOW, retention=timedelta(days=180), batch_size=5000
            )
            == 0
        )

    async def test_it_deletes_at_most_one_batch(self, security_event_repo):
        """The caller loops; one call must not drain more than its batch."""
        await self._seed(security_event_repo, *[timedelta(days=200)] * 10)

        deleted = await service.purge_expired_security_events(
            security_event_repo, now=NOW, retention=timedelta(days=180), batch_size=4
        )

        assert deleted == 4
        assert len(security_event_repo.events) == 6
