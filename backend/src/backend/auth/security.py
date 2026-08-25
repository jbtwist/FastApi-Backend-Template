import secrets
import uuid
from datetime import datetime
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
    """Hash a password with argon2 for storage."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a stored hash.

    Returns `False` instead of raising on a malformed or mismatched hash, so
    callers can always compare against a real or dummy hash (see
    `DUMMY_PASSWORD_HASH`) without a try/except of their own.
    """
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


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


def generate_refresh_token(*, config: AuthConfig) -> str:
    """Generate a random opaque refresh token.

    Not a JWT — verified only against its stored hash.
    """
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    """Hash a raw refresh token for storage/lookup. Unsalted: the token itself is high-entropy."""
    return sha256(raw_token.encode("utf-8")).hexdigest()


def generate_email_verification_token(*, config: AuthConfig) -> str:
    """Generate a random opaque email-verification token (mirrors `generate_refresh_token`)."""
    return secrets.token_urlsafe(32)


def hash_email_verification_token(raw_token: str) -> str:
    """Hash a raw email-verification token for storage/lookup."""
    return sha256(raw_token.encode("utf-8")).hexdigest()
