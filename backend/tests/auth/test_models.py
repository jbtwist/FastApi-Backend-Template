"""Real-Postgres checks on `user` columns."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_user_persists_without_a_password_hash(db: AsyncSession):
    """A provider-created account has no password, so the row stores none."""
    user = User(email=f"{uuid.uuid4()}@example.com", password_hash=None)
    db.add(user)
    await db.flush()
    user_id = user.id
    db.expire_all()

    stored = await db.get(User, user_id)

    assert stored.password_hash is None
