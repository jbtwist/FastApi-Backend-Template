"""Real-Postgres tests for `SqlOAuthIdentityRepository`.

One provider identity per account is guaranteed by a unique constraint, not by a
service-level check, so these run against actual SQL. Each test runs inside a
transaction that the `db` fixture rolls back.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User
from backend.auth.oauth.repository import SqlOAuthIdentityRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _add_user(db: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def user(db: AsyncSession) -> User:
    return await _add_user(db)


@pytest.fixture
def repo(db: AsyncSession) -> SqlOAuthIdentityRepository:
    return SqlOAuthIdentityRepository(db)


async def _link(repo, user_id, *, provider="google", provider_subject="subject-1"):
    return await repo.create(
        user_id=user_id,
        provider=provider,
        provider_subject=provider_subject,
        email_at_link="ada@example.com",
        is_private_relay=False,
        display_name=None,
    )


async def test_create_then_get_by_provider_subject_round_trips(db, repo, user):
    created = await repo.create(
        user_id=user.id,
        provider="apple",
        provider_subject="001234.abcd",
        email_at_link="x7@privaterelay.appleid.com",
        is_private_relay=True,
        display_name="Ada Lovelace",
    )
    created_id, user_id = created.id, user.id
    db.expire_all()

    found = await repo.get_by_provider_subject("apple", "001234.abcd")

    assert found is not None
    assert found.id == created_id
    assert found.user_id == user_id
    assert found.email_at_link == "x7@privaterelay.appleid.com"
    assert found.is_private_relay is True
    assert found.display_name == "Ada Lovelace"
    assert found.created_at is not None
    assert found.last_authenticated_at is None


async def test_get_by_provider_subject_needs_both_parts_to_match(repo, user):
    await _link(repo, user.id, provider="google", provider_subject="subject-1")

    assert await repo.get_by_provider_subject("apple", "subject-1") is None
    assert await repo.get_by_provider_subject("google", "subject-2") is None


async def test_one_subject_under_two_providers_is_two_identities(repo, user):
    google = await _link(repo, user.id, provider="google", provider_subject="subject-1")
    apple = await _link(repo, user.id, provider="apple", provider_subject="subject-1")

    assert google.id != apple.id


async def test_duplicate_provider_subject_is_refused_by_the_database(db, repo, user):
    other = await _add_user(db)
    await _link(repo, user.id)

    with pytest.raises(IntegrityError, match="oauth_identity_provider_subject_key"):
        async with db.begin_nested():
            await _link(repo, other.id)


async def test_mark_authenticated_records_the_sign_in_time(db, repo, user):
    created = await _link(repo, user.id)

    await repo.mark_authenticated(created.id, authenticated_at=NOW)
    await db.flush()
    db.expire_all()

    found = await repo.get_by_provider_subject("google", "subject-1")
    assert found.last_authenticated_at == NOW
