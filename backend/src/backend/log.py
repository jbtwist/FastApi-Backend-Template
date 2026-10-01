"""Structured application logging: configuration, formatters, and the audit event API.

Every record goes to stdout as a single line. The app is stateless and scales
horizontally, so log files, rotation and shipping belong to whatever runs the
process, not to the process itself.

Two kinds of record travel through here. An `audit_event` is a deliberate record
of something the app did — a user registered, a refresh token was reused, a row
was written — emitted through an `AuditLogger` and carrying its data as fields
rather than as prose. Everything else is an ordinary `logging` call from any module, and
formats as a plain message.

Each area writes its audit events through its own child of `backend.audit`, made
once per module with `audit = audit_logger("auth")` and called like any logger:
`audit.info("login.failed", reason=...)`. A line then names its area, a handler or
filter on `backend.audit` still sees every area, and one area, such as the
high-volume `db` row writes, can be quietened without touching the others. One
action logs one event: its consequences, such as revoked sessions, are part of
what the event means, and the `db` row writes carry the detail.

Nothing that reaches a log may carry a credential or an address. `AuditLogger`
scrubs a fixed set of field names before the record exists, so a caller that
passes `token_hash=` or `email=` cannot leak one by accident. The denylist matches
on the *name* of a field, never on the shape of its value: a secret passed under
some other name is not detected.
"""

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import cache
from typing import Any

AUDIT_LOGGER_NAME = "backend.audit"
CORRELATION_ID_HEADER = b"x-request-id"
MAX_CORRELATION_ID_LENGTH = 64
USER_AGENT_HEADER = b"user-agent"
MAX_USER_AGENT_LENGTH = 512
SCRUBBED = "***"

SENSITIVE_FIELDS = frozenset(
    {
        "access_token",
        "authorization",
        "email",
        "jwt",
        "password",
        "password_hash",
        "raw_token",
        "refresh_token",
        "secret",
        "token",
        "token_hash",
    }
)

_UNSAFE_CORRELATION_ID = re.compile(r"[^A-Za-z0-9_-]")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
ip_address: ContextVar[str | None] = ContextVar("ip_address", default=None)
user_agent: ContextVar[str | None] = ContextVar("user_agent", default=None)


class AuditLogger:
    """Writes one area's `audit_event`s, with their data as structured fields.

    Fields land in one `audit_fields` dict on the record rather than as separate
    attributes, so a caller can pass keys like `message` or `name` without
    colliding with `logging`'s own record attributes.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    @property
    def name(self) -> str:
        return self._logger.name

    def info(self, event: str, **fields: Any) -> None:
        """Record `event` at `INFO`."""
        self._log(logging.INFO, event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        """Record `event` at `WARNING`, for anything a human should chase."""
        self._log(logging.WARNING, event, fields)

    def _log(self, level: int, event: str, fields: dict[str, Any]) -> None:
        self._logger.log(level, event, extra={"event": event, "audit_fields": _scrub(fields)})


@cache
def audit_logger(area: str) -> AuditLogger:
    """Return the audit logger for one area, a child of `backend.audit`."""
    return AuditLogger(logging.getLogger(f"{AUDIT_LOGGER_NAME}.{area}"))


def new_correlation_id() -> str:
    """Mint an id for a request or task that arrived without one."""
    return uuid.uuid4().hex


def _scrub(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (SCRUBBED if key.lower() in SENSITIVE_FIELDS else value)
        for key, value in fields.items()
    }


class CorrelationIdFilter(logging.Filter):
    """Stamps the active `correlation_id`, `ip_address` and `user_agent` onto every record.

    A filter rather than a formatter lookup, so the value is read while the
    emitting context is still current.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id.get()
        record.ip_address = ip_address.get()
        record.user_agent = user_agent.get()
        return True


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line.

    Caller fields nest under `fields` rather than flattening into the envelope,
    so an audit field named `level` or `timestamp` cannot shadow the real one.
    Only an `audit_event` carries `ip_address` and `user_agent`.
    Values `json` cannot serialise — a `UUID`, a `datetime` — fall back to `str`.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", None),
        }

        event = getattr(record, "event", None)
        if event is None:
            payload["message"] = record.getMessage()
        else:
            payload["event"] = event
            payload["ip_address"] = getattr(record, "ip_address", None)
            payload["user_agent"] = getattr(record, "user_agent", None)

        fields = getattr(record, "audit_fields", None)
        if fields:
            payload["fields"] = fields

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class ConsoleLogFormatter(logging.Formatter):
    """A readable line for local development: `HH:MM:SS LEVEL event key=value`.

    Nothing here is escaped, so control characters are stripped from the
    caller-supplied `user_agent`: a newline in it would forge a second line.
    """

    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created, UTC).strftime("%H:%M:%S")
        head = getattr(record, "event", None) or record.getMessage()
        parts = [f"{stamp} {record.levelname:<8} {head}"]

        fields = getattr(record, "audit_fields", None)
        if fields:
            parts.append(" ".join(f"{key}={value}" for key, value in fields.items()))

        if getattr(record, "event", None) is not None:
            client_ip_address = getattr(record, "ip_address", None)
            if client_ip_address:
                parts.append(f"ip_address={client_ip_address}")
            client_user_agent = getattr(record, "user_agent", None)
            if client_user_agent:
                parts.append(f"user_agent={_CONTROL_CHARACTERS.sub('', client_user_agent)}")

        active_correlation_id = getattr(record, "correlation_id", None)
        if active_correlation_id:
            parts.append(f"[{active_correlation_id}]")

        line = " ".join(parts)
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


_FORMATTERS: dict[str, type[logging.Formatter]] = {
    "json": JsonLogFormatter,
    "console": ConsoleLogFormatter,
}

_LIBRARY_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error", "celery")


def configure_logging(*, level: str, log_format: str) -> None:
    """Point the root logger at stdout with one handler in the requested format.

    Replaces any handler already installed, so calling it twice leaves exactly
    one — and so it can take the root logger back from a library that configured
    it first, which is what the Celery worker needs.

    Libraries that install their own handler and stop propagating are pointed
    back at the root, so one process writes one format. Without that, uvicorn's
    access lines land on stdout as plain text beside the JSON.

    Raises:
        ValueError: `log_format` is neither `json` nor `console`.
    """
    formatter = _FORMATTERS.get(log_format)
    if formatter is None:
        raise ValueError(
            f"unknown log_format {log_format!r}; expected one of {sorted(_FORMATTERS)}"
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter())
    handler.addFilter(CorrelationIdFilter())

    root = logging.getLogger()
    for installed in root.handlers[:]:
        root.removeHandler(installed)
    root.addHandler(handler)
    root.setLevel(level.upper())

    for name in _LIBRARY_LOGGERS:
        library_logger = logging.getLogger(name)
        library_logger.handlers.clear()
        library_logger.propagate = True


def sanitize_correlation_id(raw: str) -> str:
    """Reduce a caller-supplied id to safe characters, capped in length.

    An inbound `X-Request-ID` is attacker-controlled and ends up in a log line;
    unrestricted, a newline in it would forge a second record.
    """
    cleaned = _UNSAFE_CORRELATION_ID.sub("", raw)[:MAX_CORRELATION_ID_LENGTH]
    return cleaned or new_correlation_id()


class CorrelationIdMiddleware:
    """Gives every request a `correlation_id`, `ip_address` and `user_agent` for its log lines.

    Pure ASGI rather than `BaseHTTPMiddleware`: the context variables are set in
    the same task that runs the endpoint, with no task hop in between. Logs
    nothing itself.

    `ip_address` is the ASGI `client`, never a header. Behind a reverse proxy,
    run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy>`; trusting a
    raw `X-Forwarded-For` would let any caller choose the address it is logged as.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        inbound = headers.get(CORRELATION_ID_HEADER)
        value = (
            sanitize_correlation_id(inbound.decode("latin-1")) if inbound else new_correlation_id()
        )
        client = scope.get("client")
        agent = headers.get(USER_AGENT_HEADER)

        tokens = [
            (correlation_id, correlation_id.set(value)),
            (ip_address, ip_address.set(client[0] if client else None)),
            (
                user_agent,
                user_agent.set(agent.decode("latin-1")[:MAX_USER_AGENT_LENGTH] if agent else None),
            ),
        ]
        try:
            await self.app(scope, receive, send)
        finally:
            for var, token in reversed(tokens):
                var.reset(token)
