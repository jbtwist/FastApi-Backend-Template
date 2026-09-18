from datetime import timedelta

import fakeredis.aioredis
import pytest

from backend.auth.oauth.state import RedisSignInStateStore, SignInAttempt

ATTEMPT = SignInAttempt(provider="google", nonce="nonce-value", redirect_target="/(app)")


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(server=fakeredis.aioredis.FakeServer())


@pytest.fixture
def store(redis) -> RedisSignInStateStore:
    return RedisSignInStateStore(redis)


async def test_a_saved_attempt_is_consumed_intact(store):
    await store.save("state-1", ATTEMPT, ttl=timedelta(minutes=10))

    assert await store.consume("state-1") == ATTEMPT


async def test_an_attempt_is_consumed_at_most_once(store):
    await store.save("state-1", ATTEMPT, ttl=timedelta(minutes=10))
    await store.consume("state-1")

    assert await store.consume("state-1") is None


async def test_an_unknown_state_has_no_attempt(store):
    assert await store.consume("never-saved") is None


async def test_is_keyed_by_state_and_expires_with_the_attempt(store, redis):
    await store.save("state-1", ATTEMPT, ttl=timedelta(minutes=10))

    assert await redis.exists("oauth:state:state-1") == 1
    assert 0 < await redis.ttl("oauth:state:state-1") <= 600


async def test_attempts_are_kept_apart_by_state(store):
    other = SignInAttempt(provider="apple", nonce="other-nonce", redirect_target="/")
    await store.save("state-1", ATTEMPT, ttl=timedelta(minutes=10))
    await store.save("state-2", other, ttl=timedelta(minutes=10))

    assert await store.consume("state-2") == other
    assert await store.consume("state-1") == ATTEMPT
