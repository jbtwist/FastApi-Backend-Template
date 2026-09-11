import asyncio
import contextlib
import secrets
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from hashlib import sha256

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from backend.auth.config import AuthConfig
from backend.auth.exceptions import AccessTokenExpired, InvalidAccessToken

_password_hasher = PasswordHasher()

# Valid argon2 hash of a value nobody can log in with, used to pay the same
# hashing cost on verifying hash operations.
DUMMY_PASSWORD_HASH = _password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    """Hash a password with argon2 for storage.

    argon2id at `argon2-cffi`'s own defaults, which track the
    [OWASP Password Storage Cheat Sheet][owasp] recommendation.

    [owasp]: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
    """
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a stored hash.

    Returns `False` instead of raising on a malformed or mismatched hash, so
    callers can always compare against a real or dummy hash (see
    `DUMMY_PASSWORD_HASH`) without a try/except of their own.
    """
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError, InvalidHashError:
        return False


@contextlib.asynccontextmanager
async def minimum_duration(minimum: timedelta) -> AsyncGenerator:
    """Pad the enclosed work to at least `minimum` wall-clock time, whatever its outcome.

    How an enumeration-safe endpoint enforces its response floor (e.g.
    `REGISTER_RESPONSE_FLOOR`), so how long a request took can't reveal which
    path it took. Pads when the work raises, too. Best-effort defence against a
    timing oracle — not a hard guarantee against scheduler jitter. A no-op when
    `minimum` is zero.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        remaining = minimum.total_seconds() - (time.perf_counter() - start)
        if remaining > 0:
            await asyncio.sleep(remaining)


def create_access_token(sub: str, *, config: AuthConfig, now: datetime) -> str:
    """Issue a signed JWT access token for `sub`, expiring after `config.ACCESS_TOKEN_EXP`."""
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + config.ACCESS_TOKEN_EXP).timestamp()),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALG)


def decode_access_token(token: str, *, config: AuthConfig) -> dict:
    """Verify and decode a JWT access token.

    Raises:
        AccessTokenExpired: the token's `exp` claim is in the past.
        InvalidAccessToken: the signature is invalid, `exp` is missing, or
            `sub` is missing or not a UUID.
    """
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=[config.JWT_ALG],
            options={"require": ["exp"]},
        )
    except ExpiredSignatureError as exc:
        raise AccessTokenExpired from exc
    except InvalidTokenError as exc:
        raise InvalidAccessToken from exc

    if "sub" not in payload:
        raise InvalidAccessToken

    try:
        uuid.UUID(payload["sub"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidAccessToken from exc

    return payload


def generate_opaque_token() -> str:
    """A high-entropy URL-safe token for the DB-backed token tables.

    Used for refresh, email-verification and password-reset tokens alike. Not a
    JWT — verified only against its stored hash (see `hash_opaque_token`).
    """
    return secrets.token_urlsafe(32)


def hash_opaque_token(raw_token: str) -> str:
    """SHA-256 hex of an opaque token, for storage and lookup.

    Unsalted: the token is already high-entropy. Only the hash is persisted, so
    a database leak doesn't expose usable tokens.
    """
    return sha256(raw_token.encode("utf-8")).hexdigest()
