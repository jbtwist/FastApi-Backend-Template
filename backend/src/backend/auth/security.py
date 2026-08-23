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
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError, InvalidHashError:
        return False


def create_access_token(sub: str, *, config: AuthConfig, now: datetime) -> str:
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + config.ACCESS_TOKEN_EXP).timestamp()),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALG)


def decode_access_token(token: str, *, config: AuthConfig) -> dict:
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
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()
