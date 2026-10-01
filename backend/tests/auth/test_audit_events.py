"""The `audit_event` records each auth action leaves on the `backend.audit` logger."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from backend.auth import service
from backend.auth.exceptions import EmailNotVerified, InvalidCredentials
from backend.auth.security import hash_opaque_token

NOW = datetime(2026, 1, 1, tzinfo=UTC)
AFTER_GRACE = NOW + timedelta(minutes=5)
PASSWORD = "s3cret-pw"


def _events(records: list[logging.LogRecord]) -> list[str]:
    """Audit event names, leaving out the per-row `db_write` records."""
    return [record.event for record in records if record.event != "db_write"]


def _only(records: list[logging.LogRecord], event: str) -> logging.LogRecord:
    """The one record named `event`, which must come from the `auth` audit logger."""
    [record] = [record for record in records if record.event == event]
    assert record.name == "backend.audit.auth"
    return record


@pytest.fixture
async def unverified_user(user_repo):
    return await service.register_user(user_repo, email="ada@example.com", password=PASSWORD)


@pytest.fixture
async def verified_user(user_repo, unverified_user):
    await user_repo.mark_email_verified(unverified_user.id, verified_at=NOW)
    return await user_repo.get_by_id(unverified_user.id)


@pytest.fixture
async def session(refresh_token_repo, verified_user, auth_config):
    return await service.issue_token_pair(
        refresh_token_repo, verified_user, config=auth_config, now=NOW
    )


@pytest.fixture
async def family_id(refresh_token_repo, session):
    record = await refresh_token_repo.get_by_hash(hash_opaque_token(session.refresh_token))
    return record.family_id


class TestRegistration:
    async def test_a_new_account_records_the_method(self, user_repo, captured_records):
        user = await service.register_user(user_repo, email="ada@example.com", password=PASSWORD)

        record = _only(captured_records, "user.registered")
        assert record.audit_fields == {"user_id": user.id, "method": "password"}


class TestLogin:
    async def test_success_records_the_method(self, user_repo, verified_user, captured_records):
        await service.authenticate_user(user_repo, email="ada@example.com", password=PASSWORD)

        record = _only(captured_records, "login.succeeded")
        assert record.audit_fields == {"user_id": verified_user.id, "method": "password"}

    async def test_a_wrong_password_on_a_real_account_names_the_account(
        self, user_repo, verified_user, captured_records
    ):
        with pytest.raises(InvalidCredentials):
            await service.authenticate_user(user_repo, email="ada@example.com", password="nope")

        record = _only(captured_records, "login.failed")
        assert record.audit_fields == {
            "reason": "invalid_credentials",
            "user_id": verified_user.id,
        }

    async def test_a_password_attempt_on_a_passwordless_account_names_the_account(
        self, user_repo, captured_records
    ):
        """An account created through a provider has no password to match."""
        user = await user_repo.create(email="ada@example.com", password_hash=None)

        with pytest.raises(InvalidCredentials):
            await service.authenticate_user(user_repo, email="ada@example.com", password=PASSWORD)

        assert _only(captured_records, "login.failed").audit_fields.get("user_id") == user.id

    async def test_an_unknown_address_names_no_account(self, user_repo, captured_records):
        with pytest.raises(InvalidCredentials):
            await service.authenticate_user(
                user_repo, email="nobody@example.com", password=PASSWORD
            )

        record = _only(captured_records, "login.failed")
        assert record.audit_fields == {"reason": "invalid_credentials"}

    async def test_an_unverified_account_is_recorded(
        self, user_repo, unverified_user, captured_records
    ):
        with pytest.raises(EmailNotVerified):
            await service.authenticate_user(user_repo, email="ada@example.com", password=PASSWORD)

        record = _only(captured_records, "login.failed")
        assert record.audit_fields == {
            "reason": "email_not_verified",
            "user_id": unverified_user.id,
        }


class TestLogout:
    async def test_logout_is_one_event(
        self, refresh_token_repo, session, family_id, verified_user, captured_records
    ):
        await service.logout(refresh_token_repo, session.refresh_token, now=NOW)

        assert _events(captured_records) == ["logout"]
        assert _only(captured_records, "logout").audit_fields == {
            "user_id": verified_user.id,
            "family_id": family_id,
        }

    async def test_an_unknown_token_records_nothing(self, refresh_token_repo, captured_records):
        await service.logout(refresh_token_repo, "never-issued-token", now=NOW)

        assert _events(captured_records) == []


class TestReuseDetection:
    async def test_reuse_is_a_warning_naming_the_family(
        self, refresh_token_repo, session, family_id, auth_config, captured_records
    ):
        await service.rotate_refresh_token(
            refresh_token_repo, session.refresh_token, config=auth_config, now=NOW
        )

        await service.rotate_refresh_token(
            refresh_token_repo, session.refresh_token, config=auth_config, now=AFTER_GRACE
        )

        record = _only(captured_records, "token.reuse_detected")
        assert record.levelno == logging.WARNING
        assert record.audit_fields["family_id"] == family_id


class TestPasswordReset:
    async def test_completing_is_one_event(
        self,
        password_reset_token_repo,
        user_repo,
        refresh_token_repo,
        email_outbox_repo,
        verified_user,
        auth_config,
        captured_records,
    ):
        entry = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="ada@example.com",
            config=auth_config,
            now=NOW,
        )
        assert _only(captured_records, "password.reset_requested")
        captured_records.clear()

        await service.reset_password(
            password_reset_token_repo,
            user_repo,
            refresh_token_repo,
            entry.token,
            new_password="a-brand-new-passphrase",
            now=NOW,
        )

        assert _events(captured_records) == ["password.reset_completed"]
        assert _only(captured_records, "password.reset_completed").audit_fields == {
            "user_id": verified_user.id
        }
