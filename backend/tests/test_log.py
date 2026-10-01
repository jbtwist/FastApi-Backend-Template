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
    AUDIT_LOGGER_NAME,
    MAX_CORRELATION_ID_LENGTH,
    MAX_USER_AGENT_LENGTH,
    SCRUBBED,
    ConsoleLogFormatter,
    CorrelationIdFilter,
    CorrelationIdMiddleware,
    JsonLogFormatter,
    audit_logger,
    configure_logging,
    correlation_id,
    ip_address,
    new_correlation_id,
    sanitize_correlation_id,
    user_agent,
)


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


class TestAuditLogger:
    """`audit_logger(area).info(event, **fields)` and its `warning` twin."""

    @pytest.fixture
    def audit(self):
        return audit_logger("test")

    def test_event_name_becomes_the_message(self, audit, captured_records):
        audit.info("user.registered")
        assert captured_records[0].getMessage() == "user.registered"
        assert captured_records[0].event == "user.registered"

    def test_fields_land_in_audit_fields(self, audit, captured_records):
        user_id = uuid.uuid4()
        audit.info("user.registered", user_id=user_id, source="web")
        assert captured_records[0].audit_fields == {"user_id": user_id, "source": "web"}

    @pytest.mark.parametrize(
        "field",
        ["password", "token", "token_hash", "refresh_token", "email", "secret", "authorization"],
    )
    def test_sensitive_fields_are_scrubbed(self, audit, captured_records, field):
        audit.info("login.failed", **{field: "super-secret-value"})
        assert captured_records[0].audit_fields[field] == SCRUBBED

    def test_sensitive_fields_are_scrubbed_at_warning_too(self, audit, captured_records):
        audit.warning("token.reuse_detected", token="super-secret-value")
        assert captured_records[0].audit_fields["token"] == SCRUBBED

    def test_scrubbing_ignores_case(self, audit, captured_records):
        audit.info("login.failed", Password="hunter2", TOKEN="abc")
        assert captured_records[0].audit_fields == {"Password": SCRUBBED, "TOKEN": SCRUBBED}

    def test_a_secret_under_an_unlisted_name_is_not_detected(self, audit, captured_records):
        """The denylist matches names, never values. Documented limitation, pinned here."""
        audit.info("login.failed", session_blob="hunter2")
        assert captured_records[0].audit_fields["session_blob"] == "hunter2"

    def test_reserved_logging_attribute_names_are_safe_as_fields(self, audit, captured_records):
        """Nesting under `audit_fields` is what keeps these from colliding with the record."""
        audit.info("db_write", message="anything", name="anything", args="anything")
        record = captured_records[0]
        assert record.name == "backend.audit.test"
        assert record.audit_fields == {
            "message": "anything",
            "name": "anything",
            "args": "anything",
        }

    def test_the_method_sets_the_level(self, audit, captured_records):
        audit.info("a.b")
        audit.warning("c.d")
        assert [r.levelno for r in captured_records] == [logging.INFO, logging.WARNING]

    def test_an_area_logger_is_a_child_of_the_audit_logger(self):
        assert audit_logger("auth").name == f"{AUDIT_LOGGER_NAME}.auth"

    def test_the_same_area_returns_the_same_logger(self):
        assert audit_logger("auth") is audit_logger("auth")

    def test_an_area_event_reaches_a_handler_on_the_parent(self, captured_records):
        """One handler on `backend.audit` still sees every area."""
        audit_logger("auth").info("login.failed")
        audit_logger("db").info("db_write")

        assert [record.name for record in captured_records] == [
            "backend.audit.auth",
            "backend.audit.db",
        ]

    def test_an_area_can_be_quietened_on_its_own(self, captured_records):
        db = logging.getLogger(f"{AUDIT_LOGGER_NAME}.db")
        previous = db.level
        db.setLevel(logging.WARNING)
        try:
            audit_logger("db").info("db_write")
            audit_logger("auth").info("login.failed")
        finally:
            db.setLevel(previous)

        assert [record.event for record in captured_records] == ["login.failed"]

    def test_the_json_logger_field_names_the_area(self, captured_records):
        audit_logger("oauth").info("oauth.link_requested")

        payload = json.loads(JsonLogFormatter().format(captured_records[0]))

        assert payload["logger"] == "backend.audit.oauth"


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

    def test_an_audit_record_carries_the_client_context(self, make_record):
        record = make_record(
            event="login.succeeded", ip_address="203.0.113.7", user_agent="curl/8.0"
        )
        payload = json.loads(JsonLogFormatter().format(record))
        assert payload["ip_address"] == "203.0.113.7"
        assert payload["user_agent"] == "curl/8.0"

    def test_an_ordinary_record_leaves_the_client_context_out(self, make_record):
        """Library lines repeat nothing per request; the access log has the address."""
        record = make_record(ip_address="203.0.113.7", user_agent="curl/8.0")
        payload = json.loads(JsonLogFormatter().format(record))
        assert "ip_address" not in payload
        assert "user_agent" not in payload


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

    def test_an_audit_record_shows_the_client_context(self, make_record):
        record = make_record(event="a.b", ip_address="203.0.113.7", user_agent="curl/8.0")
        line = ConsoleLogFormatter().format(record)
        assert "ip_address=203.0.113.7" in line
        assert "user_agent=curl/8.0" in line

    def test_control_characters_in_the_user_agent_cannot_forge_a_line(self, make_record):
        """The header is caller-controlled and console output is not escaped."""
        record = make_record(event="a.b", user_agent="evil\n12:00:00 INFO     forged.event")
        line = ConsoleLogFormatter().format(record)
        assert "\n" not in line
        assert "\r" not in line


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

    def test_stamps_the_client_context(self, make_record):
        ip_token = ip_address.set("203.0.113.7")
        agent_token = user_agent.set("curl/8.0")
        try:
            record = make_record()
            CorrelationIdFilter().filter(record)
        finally:
            ip_address.reset(ip_token)
            user_agent.reset(agent_token)
        assert record.ip_address == "203.0.113.7"
        assert record.user_agent == "curl/8.0"


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


class TestClientContext:
    """`CorrelationIdMiddleware` also records who is calling, for audit lines."""

    @pytest.fixture
    def seen(self) -> list[tuple[str | None, str | None]]:
        return []

    @pytest.fixture
    def middleware(self, seen):
        async def app(scope, receive, send):
            seen.append((ip_address.get(), user_agent.get()))

        return CorrelationIdMiddleware(app)

    @staticmethod
    def _scope(*, client=("203.0.113.7", 51234), headers=None) -> dict:
        return {"type": "http", "client": client, "headers": headers or []}

    @pytest.mark.asyncio
    async def test_the_client_address_is_set_from_the_asgi_client(self, middleware, seen):
        await middleware(self._scope(), None, None)
        assert seen[0][0] == "203.0.113.7"

    @pytest.mark.asyncio
    async def test_a_forwarded_header_is_not_trusted(self, middleware, seen):
        """Only uvicorn's proxy handling may rewrite the client, never a raw header."""
        scope = self._scope(headers=[(b"x-forwarded-for", b"198.51.100.1")])
        await middleware(scope, None, None)
        assert seen[0][0] == "203.0.113.7"

    @pytest.mark.asyncio
    async def test_the_user_agent_is_set_from_the_header(self, middleware, seen):
        await middleware(self._scope(headers=[(b"user-agent", b"Mozilla/5.0")]), None, None)
        assert seen[0][1] == "Mozilla/5.0"

    @pytest.mark.asyncio
    async def test_a_long_user_agent_is_truncated(self, middleware, seen):
        long_agent = b"x" * (MAX_USER_AGENT_LENGTH + 100)
        await middleware(self._scope(headers=[(b"user-agent", long_agent)]), None, None)
        assert seen[0][1] == "x" * MAX_USER_AGENT_LENGTH

    @pytest.mark.asyncio
    async def test_no_client_and_no_header_leave_both_unset(self, middleware, seen):
        await middleware(self._scope(client=None), None, None)
        assert seen[0] == (None, None)

    @pytest.mark.asyncio
    async def test_both_are_reset_afterwards(self, middleware):
        await middleware(self._scope(headers=[(b"user-agent", b"curl/8.0")]), None, None)
        assert ip_address.get() is None
        assert user_agent.get() is None
