"""Tests for the structured logging module.

Coverage backfill for `backend.log`, which shipped without any. These exercise
existing behaviour, so they pass rather than run red.

Every test that touches the root logger restores it afterwards, because
`configure_logging` replaces handlers process-wide and pytest's own capture
plugin lives on the same logger.
"""

import json
import logging
import uuid
from datetime import UTC, datetime

import pytest

from backend.log import (
    MAX_CORRELATION_ID_LENGTH,
    SCRUBBED,
    ConsoleLogFormatter,
    CorrelationIdFilter,
    CorrelationIdMiddleware,
    JsonLogFormatter,
    configure_logging,
    correlation_id,
    log_event,
    new_correlation_id,
    sanitize_correlation_id,
)


@pytest.fixture
def captured_records() -> list[logging.LogRecord]:
    """Records emitted on the audit logger, captured without touching handlers."""
    collected: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            collected.append(record)

    audit_logger = logging.getLogger("backend.audit")
    handler = _Collector()
    audit_logger.addHandler(handler)
    previous_level = audit_logger.level
    audit_logger.setLevel(logging.DEBUG)
    try:
        yield collected
    finally:
        audit_logger.removeHandler(handler)
        audit_logger.setLevel(previous_level)


@pytest.fixture
def restore_root_logger():
    """Snapshot the root logger so `configure_logging` cannot leak across tests."""
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture
def make_record():
    """Build a LogRecord the way `logging` would, with optional extras attached."""

    def _make(
        message: str = "hello", *, level: int = logging.INFO, **extras: object
    ) -> logging.LogRecord:
        record = logging.LogRecord(
            name="backend.test",
            level=level,
            pathname=__file__,
            lineno=1,
            msg=message,
            args=(),
            exc_info=None,
        )
        for key, value in extras.items():
            setattr(record, key, value)
        return record

    return _make


class TestLogEvent:
    def test_event_name_becomes_the_message(self, captured_records):
        log_event("user.registered")
        assert captured_records[0].getMessage() == "user.registered"
        assert captured_records[0].event == "user.registered"

    def test_fields_land_in_audit_fields(self, captured_records):
        user_id = uuid.uuid4()
        log_event("user.registered", user_id=user_id, source="web")
        assert captured_records[0].audit_fields == {"user_id": user_id, "source": "web"}

    @pytest.mark.parametrize(
        "field",
        ["password", "token", "token_hash", "refresh_token", "email", "secret", "authorization"],
    )
    def test_sensitive_fields_are_scrubbed(self, captured_records, field):
        log_event("login.failed", **{field: "super-secret-value"})
        assert captured_records[0].audit_fields[field] == SCRUBBED

    def test_scrubbing_ignores_case(self, captured_records):
        log_event("login.failed", Password="hunter2", TOKEN="abc")
        assert captured_records[0].audit_fields == {"Password": SCRUBBED, "TOKEN": SCRUBBED}

    def test_a_secret_under_an_unlisted_name_is_not_detected(self, captured_records):
        """The denylist matches names, never values. Documented limitation, pinned here."""
        log_event("login.failed", session_blob="hunter2")
        assert captured_records[0].audit_fields["session_blob"] == "hunter2"

    def test_reserved_logging_attribute_names_are_safe_as_fields(self, captured_records):
        """Nesting under `audit_fields` is what keeps these from colliding with the record."""
        log_event("db_write", message="anything", name="anything", args="anything")
        record = captured_records[0]
        assert record.name == "backend.audit"
        assert record.audit_fields == {
            "message": "anything",
            "name": "anything",
            "args": "anything",
        }

    def test_level_is_reserved_by_the_signature_not_available_as_a_field(self):
        """`level` is keyword-only on `log_event`, so it can never be a field name."""
        with pytest.raises(TypeError):
            log_event("db_write", level="anything")

    def test_level_defaults_to_info_and_is_overridable(self, captured_records):
        log_event("a.b")
        log_event("c.d", level=logging.WARNING)
        assert [r.levelno for r in captured_records] == [logging.INFO, logging.WARNING]


class TestJsonLogFormatter:
    def test_emits_one_line_of_valid_json(self, make_record):
        line = JsonLogFormatter().format(make_record("plain message"))
        assert "\n" not in line
        assert json.loads(line)["message"] == "plain message"

    def test_envelope_carries_level_logger_and_timestamp(self, make_record):
        payload = json.loads(JsonLogFormatter().format(make_record(level=logging.WARNING)))
        assert payload["level"] == "WARNING"
        assert payload["logger"] == "backend.test"
        datetime.fromisoformat(payload["timestamp"])

    def test_an_audit_record_carries_event_instead_of_message(self, make_record):
        record = make_record("user.registered", event="user.registered")
        payload = json.loads(JsonLogFormatter().format(record))
        assert payload["event"] == "user.registered"
        assert "message" not in payload

    def test_caller_fields_cannot_shadow_the_envelope(self, make_record):
        record = make_record(event="a.b", audit_fields={"level": "bogus", "timestamp": "bogus"})
        payload = json.loads(JsonLogFormatter().format(record))
        assert payload["level"] == "INFO"
        assert payload["fields"] == {"level": "bogus", "timestamp": "bogus"}

    def test_unserialisable_values_fall_back_to_str(self, make_record):
        user_id = uuid.uuid4()
        moment = datetime(2026, 1, 1, tzinfo=UTC)
        record = make_record(event="a.b", audit_fields={"user_id": user_id, "at": moment})
        payload = json.loads(JsonLogFormatter().format(record))
        assert payload["fields"] == {"user_id": str(user_id), "at": str(moment)}

    def test_empty_fields_are_omitted(self, make_record):
        payload = json.loads(JsonLogFormatter().format(make_record(event="a.b", audit_fields={})))
        assert "fields" not in payload

    def test_exception_is_included(self, make_record):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = make_record("failed", level=logging.ERROR)
            record.exc_info = sys.exc_info()
        payload = json.loads(JsonLogFormatter().format(record))
        assert "ValueError: boom" in payload["exception"]

    def test_correlation_id_defaults_to_none_when_unset(self, make_record):
        payload = json.loads(JsonLogFormatter().format(make_record()))
        assert payload["correlation_id"] is None


class TestConsoleLogFormatter:
    def test_renders_event_and_fields(self, make_record):
        record = make_record(event="user.registered", audit_fields={"source": "web"})
        line = ConsoleLogFormatter().format(record)
        assert "INFO" in line
        assert "user.registered" in line
        assert "source=web" in line

    def test_falls_back_to_the_message_for_an_ordinary_record(self, make_record):
        assert "plain message" in ConsoleLogFormatter().format(make_record("plain message"))

    def test_correlation_id_is_bracketed_when_present(self, make_record):
        record = make_record(event="a.b", correlation_id="abc123")
        assert "[abc123]" in ConsoleLogFormatter().format(record)

    def test_correlation_id_is_omitted_when_absent(self, make_record):
        assert "[" not in ConsoleLogFormatter().format(make_record(event="a.b"))


class TestSanitizeCorrelationId:
    def test_a_safe_id_passes_through(self):
        assert sanitize_correlation_id("abc-123_XYZ") == "abc-123_XYZ"

    @pytest.mark.parametrize("raw", ["a\nb", "a\rb", "a b", "a;b", "a\tb"])
    def test_unsafe_characters_are_stripped(self, raw):
        """An inbound X-Request-ID is attacker-controlled; a newline would forge a record."""
        assert sanitize_correlation_id(raw) == "ab"

    def test_length_is_capped(self):
        assert len(sanitize_correlation_id("a" * 500)) == MAX_CORRELATION_ID_LENGTH

    def test_an_entirely_unsafe_id_is_replaced_with_a_fresh_one(self):
        assert sanitize_correlation_id("!!!!") not in ("", "!!!!")

    def test_new_correlation_id_is_unique(self):
        assert new_correlation_id() != new_correlation_id()


class TestCorrelationIdFilter:
    def test_stamps_the_active_value(self, make_record):
        token = correlation_id.set("abc123")
        try:
            record = make_record()
            assert CorrelationIdFilter().filter(record) is True
            assert record.correlation_id == "abc123"
        finally:
            correlation_id.reset(token)

    def test_stamps_none_outside_a_request(self, make_record):
        record = make_record()
        CorrelationIdFilter().filter(record)
        assert record.correlation_id is None


class TestConfigureLogging:
    def test_installs_exactly_one_stdout_handler(self, restore_root_logger):
        configure_logging(level="INFO", log_format="json")
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonLogFormatter)

    def test_calling_it_twice_still_leaves_one_handler(self, restore_root_logger):
        configure_logging(level="INFO", log_format="json")
        configure_logging(level="INFO", log_format="console")
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, ConsoleLogFormatter)

    def test_level_is_applied(self, restore_root_logger):
        configure_logging(level="warning", log_format="json")
        assert logging.getLogger().level == logging.WARNING

    def test_an_unknown_format_is_rejected(self, restore_root_logger):
        with pytest.raises(ValueError, match="unknown log_format"):
            configure_logging(level="INFO", log_format="logfmt")

    def test_library_loggers_are_pointed_back_at_the_root(self, restore_root_logger):
        uvicorn_access = logging.getLogger("uvicorn.access")
        uvicorn_access.addHandler(logging.StreamHandler())
        uvicorn_access.propagate = False

        configure_logging(level="INFO", log_format="json")

        assert uvicorn_access.handlers == []
        assert uvicorn_access.propagate is True

    def test_the_handler_carries_the_correlation_id_filter(self, restore_root_logger):
        configure_logging(level="INFO", log_format="json")
        filters = logging.getLogger().handlers[0].filters
        assert any(isinstance(f, CorrelationIdFilter) for f in filters)


class TestCorrelationIdMiddleware:
    @pytest.fixture
    def seen(self) -> list[str | None]:
        return []

    @pytest.fixture
    def middleware(self, seen):
        async def app(scope, receive, send):
            seen.append(correlation_id.get())

        return CorrelationIdMiddleware(app)

    @staticmethod
    def _scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
        return {"type": "http", "headers": headers or []}

    @pytest.mark.asyncio
    async def test_mints_an_id_when_the_request_carries_none(self, middleware, seen):
        await middleware(self._scope(), None, None)
        assert seen[0] is not None

    @pytest.mark.asyncio
    async def test_adopts_an_inbound_request_id(self, middleware, seen):
        await middleware(self._scope([(b"x-request-id", b"abc-123")]), None, None)
        assert seen[0] == "abc-123"

    @pytest.mark.asyncio
    async def test_an_inbound_id_is_sanitized(self, middleware, seen):
        await middleware(self._scope([(b"x-request-id", b"ab\nINJECTED")]), None, None)
        assert seen[0] == "abINJECTED"

    @pytest.mark.asyncio
    async def test_the_value_is_reset_afterwards(self, middleware):
        await middleware(self._scope(), None, None)
        assert correlation_id.get() is None

    @pytest.mark.asyncio
    async def test_each_request_gets_its_own_id(self, middleware, seen):
        await middleware(self._scope(), None, None)
        await middleware(self._scope(), None, None)
        assert seen[0] != seen[1]

    @pytest.mark.asyncio
    async def test_a_non_http_scope_passes_straight_through(self, middleware, seen):
        await middleware({"type": "lifespan"}, None, None)
        assert seen == [None]
