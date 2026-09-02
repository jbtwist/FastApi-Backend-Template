from datetime import UTC, datetime

import pytest

from backend.auth import service
from backend.auth.security import hash_opaque_token as _hash_verification
from backend.mail.models import EmailOutboxStatus

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def registered_user(user_repo):
    user = await service.register_user(user_repo, email="ada@example.com", password="s3cret-pw")
    await user_repo.mark_email_verified(user.id, verified_at=NOW)
    return await user_repo.get_by_id(user.id)


class TestQueueVerificationEmail:
    async def test_creates_pending_outbox_entry_for_the_user(
        self, email_verification_token_repo, email_outbox_repo, registered_user, auth_config
    ):
        entry = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            registered_user,
            config=auth_config,
            now=NOW,
        )

        assert entry.user_id == registered_user.id
        assert entry.email == registered_user.email
        assert entry.status == EmailOutboxStatus.PENDING
        assert entry.attempts == 0

    async def test_stores_hash_of_the_same_token_placed_on_the_outbox_entry(
        self, email_verification_token_repo, email_outbox_repo, registered_user, auth_config
    ):
        entry = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            registered_user,
            config=auth_config,
            now=NOW,
        )

        stored = await email_verification_token_repo.get_by_hash(_hash_verification(entry.token))
        assert stored is not None
        assert stored.user_id == registered_user.id

    async def test_queueing_never_touches_the_email_provider(
        self, email_verification_token_repo, email_outbox_repo, registered_user, auth_config
    ):
        """Queuing only writes the outbox row; dispatch is the separate, retryable send step."""
        entry = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            registered_user,
            config=auth_config,
            now=NOW,
        )

        assert entry.status == EmailOutboxStatus.PENDING

    async def test_resending_creates_a_new_independent_entry(
        self, email_verification_token_repo, email_outbox_repo, registered_user, auth_config
    ):
        first = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            registered_user,
            config=auth_config,
            now=NOW,
        )
        second = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            registered_user,
            config=auth_config,
            now=NOW,
        )

        assert first.id != second.id
        assert first.token != second.token
