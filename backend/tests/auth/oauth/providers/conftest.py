import base64
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


@dataclass(frozen=True)
class SigningKey:
    """An RSA keypair standing in for one of a provider's published signing keys."""

    kid: str
    private_key: rsa.RSAPrivateKey

    @property
    def public_jwk(self) -> dict[str, Any]:
        """The public half, as the provider publishes it in its JWKS."""
        jwk = RSAAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        return {**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}

    def sign(self, claims: dict[str, Any]) -> str:
        """Mint an RS256 ID token carrying `claims`, headed with this key's `kid`."""
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.kid})

    def sign_with_none(self, claims: dict[str, Any]) -> str:
        """Mint an `alg: none` token: well formed, headed with this key's `kid`, not signed."""
        header = {"alg": "none", "typ": "JWT", "kid": self.kid}
        return f"{_base64url_json(header)}.{_base64url_json(claims)}."


def _base64url_json(value: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()


def generate_signing_key(kid: str) -> SigningKey:
    return SigningKey(kid, rsa.generate_private_key(public_exponent=65537, key_size=2048))


class FakeJwksEndpoint:
    """A provider's JWKS endpoint: serves the keys it currently publishes and counts fetches."""

    def __init__(self, *keys: SigningKey) -> None:
        self.keys = list(keys)
        self.fetch_count = 0

    def publish(self, *keys: SigningKey) -> None:
        """Replace the published keys, as a provider does when it rotates them."""
        self.keys = list(keys)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.fetch_count += 1
        return httpx.Response(200, json={"keys": [key.public_jwk for key in self.keys]})


class FakeClock:
    """A monotonic clock that moves only when a test moves it."""

    def __init__(self) -> None:
        self.seconds = 1_000.0

    def __call__(self) -> float:
        return self.seconds

    def advance(self, by: timedelta) -> None:
        self.seconds += by.total_seconds()


@pytest.fixture(scope="session")
def signing_key() -> SigningKey:
    """The key the provider publishes and signs genuine tokens with."""
    return generate_signing_key("signing-key-1")


@pytest.fixture(scope="session")
def rotated_signing_key() -> SigningKey:
    """A second key: the one a provider rotates to, or one it never published."""
    return generate_signing_key("signing-key-2")


@pytest.fixture(scope="session")
def forged_signing_key() -> SigningKey:
    """Claims the published key's `kid` but holds different key material: a forger's key."""
    return generate_signing_key("signing-key-1")


@pytest.fixture
def jwks_endpoint(signing_key) -> FakeJwksEndpoint:
    """A JWKS endpoint publishing `signing_key` only."""
    return FakeJwksEndpoint(signing_key)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()
