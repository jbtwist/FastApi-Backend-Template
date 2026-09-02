from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.auth import service
from backend.auth.exceptions import (
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidPasswordResetToken,
    InvalidRefreshToken,
    InvalidVerificationToken,
    PasswordResetTokenExpired,
    RefreshTokenExpired,
    RefreshTokenReuseDetected,
    VerificationTokenExpired,
)
from backend.auth.security import hash_opaque_token as _hash
from backend.mail.models import EmailKind

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def registered_user(user_repo):
    user = await service.register_user(user_repo, email="ada@example.com", password="s3cret-pw")
    await user_repo.mark_email_verified(user.id, verified_at=NOW)
    return await user_repo.get_by_id(user.id)


class TestRegisterUser:
    async def test_creates_user_with_hashed_password(self, user_repo):
        user = await service.register_user(user_repo, email="ada@example.com", password="s3cret-pw")

        assert user.email == "ada@example.com"
        assert user.password_hash != "s3cret-pw"
        assert user.password_hash.startswith("$argon2id$")

    async def test_raises_when_email_already_registered(self, user_repo, registered_user):
        with pytest.raises(EmailAlreadyRegistered):
            await service.register_user(user_repo, email="ada@example.com", password="other-pw")

    async def test_raises_when_email_already_registered_in_different_case(
        self, user_repo, registered_user
    ):
        with pytest.raises(EmailAlreadyRegistered):
            await service.register_user(user_repo, email="Ada@Example.com", password="other-pw")


class TestAuthenticateUser:
    async def test_returns_user_for_correct_credentials(self, user_repo, registered_user):
        user = await service.authenticate_user(
            user_repo, email="ada@example.com", password="s3cret-pw"
        )

        assert user.email == "ada@example.com"

    async def test_raises_for_wrong_password(self, user_repo, registered_user):
        with pytest.raises(InvalidCredentials):
            await service.authenticate_user(user_repo, email="ada@example.com", password="wrong-pw")

    async def test_raises_for_unknown_email(self, user_repo):
        with pytest.raises(InvalidCredentials):
            await service.authenticate_user(
                user_repo, email="nobody@example.com", password="whatever"
            )

    async def test_returns_user_when_login_email_case_differs_from_registration(
        self, user_repo, registered_user
    ):
        user = await service.authenticate_user(
            user_repo, email="Ada@Example.com", password="s3cret-pw"
        )

        assert user.email == "ada@example.com"

    async def test_raises_email_not_verified_for_unverified_account(self, user_repo):
        await service.register_user(user_repo, email="unverified@example.com", password="s3cret-pw")

        with pytest.raises(EmailNotVerified):
            await service.authenticate_user(
                user_repo, email="unverified@example.com", password="s3cret-pw"
            )

    async def test_wrong_password_raises_invalid_credentials_even_when_unverified(self, user_repo):
        await service.register_user(user_repo, email="unverified@example.com", password="s3cret-pw")

        with pytest.raises(InvalidCredentials):
            await service.authenticate_user(
                user_repo, email="unverified@example.com", password="wrong-pw"
            )


class TestIssueTokenPair:
    async def test_stores_hashed_refresh_token_not_raw_value(
        self, refresh_token_repo, registered_user, auth_config
    ):
        pair = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )

        stored = await refresh_token_repo.get_by_hash(_hash(pair.refresh_token))
        assert stored is not None
        assert stored.token_hash != pair.refresh_token

    async def test_sets_sliding_expiry_seven_days_out(
        self, refresh_token_repo, registered_user, auth_config
    ):
        pair = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )

        stored = await refresh_token_repo.get_by_hash(_hash(pair.refresh_token))
        assert stored.expires_at == NOW + timedelta(days=7)

    async def test_two_logins_get_different_families(
        self, refresh_token_repo, registered_user, auth_config
    ):
        pair_1 = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        pair_2 = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )

        token_1 = await refresh_token_repo.get_by_hash(_hash(pair_1.refresh_token))
        token_2 = await refresh_token_repo.get_by_hash(_hash(pair_2.refresh_token))
        assert token_1.family_id != token_2.family_id


class TestRotateRefreshToken:
    async def test_happy_path_rotates_within_same_family(
        self, refresh_token_repo, registered_user, auth_config
    ):
        original = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        original_record = await refresh_token_repo.get_by_hash(_hash(original.refresh_token))

        later = NOW + timedelta(days=1)
        rotated = await service.rotate_refresh_token(
            refresh_token_repo, original.refresh_token, config=auth_config, now=later
        )

        assert rotated.refresh_token != original.refresh_token
        new_record = await refresh_token_repo.get_by_hash(_hash(rotated.refresh_token))
        assert new_record.family_id == original_record.family_id

    async def test_happy_path_extends_sliding_window_from_rotation_time(
        self, refresh_token_repo, registered_user, auth_config
    ):
        original = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        later = NOW + timedelta(days=1)

        rotated = await service.rotate_refresh_token(
            refresh_token_repo, original.refresh_token, config=auth_config, now=later
        )

        new_record = await refresh_token_repo.get_by_hash(_hash(rotated.refresh_token))
        assert new_record.expires_at == later + timedelta(days=7)

    async def test_happy_path_marks_old_token_used(
        self, refresh_token_repo, registered_user, auth_config
    ):
        original = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )

        await service.rotate_refresh_token(
            refresh_token_repo, original.refresh_token, config=auth_config, now=NOW
        )

        old_record = await refresh_token_repo.get_by_hash(_hash(original.refresh_token))
        assert old_record.used_at == NOW

    async def test_reusing_an_already_rotated_token_is_detected_and_revokes_family(
        self, refresh_token_repo, registered_user, auth_config
    ):
        original = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        rotated = await service.rotate_refresh_token(
            refresh_token_repo, original.refresh_token, config=auth_config, now=NOW
        )

        with pytest.raises(RefreshTokenReuseDetected):
            await service.rotate_refresh_token(
                refresh_token_repo, original.refresh_token, config=auth_config, now=NOW
            )

        with pytest.raises(InvalidRefreshToken):
            await service.rotate_refresh_token(
                refresh_token_repo, rotated.refresh_token, config=auth_config, now=NOW
            )

    async def test_reuse_detection_only_burns_that_family_not_other_sessions(
        self, refresh_token_repo, registered_user, auth_config
    ):
        session_a = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        session_b = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        rotated_a = await service.rotate_refresh_token(
            refresh_token_repo, session_a.refresh_token, config=auth_config, now=NOW
        )

        with pytest.raises(RefreshTokenReuseDetected):
            await service.rotate_refresh_token(
                refresh_token_repo, session_a.refresh_token, config=auth_config, now=NOW
            )

        rotated_b = await service.rotate_refresh_token(
            refresh_token_repo, session_b.refresh_token, config=auth_config, now=NOW
        )
        assert rotated_b.refresh_token != session_b.refresh_token
        with pytest.raises(InvalidRefreshToken):
            await service.rotate_refresh_token(
                refresh_token_repo, rotated_a.refresh_token, config=auth_config, now=NOW
            )

    async def test_rotating_exactly_at_expiry_instant_raises_expired(
        self, refresh_token_repo, registered_user, auth_config
    ):
        original = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        exact_expiry = NOW + auth_config.REFRESH_TOKEN_EXP

        with pytest.raises(RefreshTokenExpired):
            await service.rotate_refresh_token(
                refresh_token_repo, original.refresh_token, config=auth_config, now=exact_expiry
            )

    async def test_expired_token_raises_and_does_not_rotate(
        self, refresh_token_repo, registered_user, auth_config
    ):
        original = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        after_expiry = NOW + auth_config.REFRESH_TOKEN_EXP + timedelta(seconds=1)

        with pytest.raises(RefreshTokenExpired):
            await service.rotate_refresh_token(
                refresh_token_repo, original.refresh_token, config=auth_config, now=after_expiry
            )

        record = await refresh_token_repo.get_by_hash(_hash(original.refresh_token))
        assert record.used_at is None

    async def test_unknown_token_raises_invalid(self, refresh_token_repo, auth_config):
        with pytest.raises(InvalidRefreshToken):
            await service.rotate_refresh_token(
                refresh_token_repo, "never-issued-token", config=auth_config, now=NOW
            )

    async def test_token_from_revoked_family_raises_invalid(
        self, refresh_token_repo, registered_user, auth_config
    ):
        original = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        await service.logout(refresh_token_repo, original.refresh_token, now=NOW)

        with pytest.raises(InvalidRefreshToken):
            await service.rotate_refresh_token(
                refresh_token_repo, original.refresh_token, config=auth_config, now=NOW
            )

    async def test_losing_the_mark_used_race_is_treated_as_reuse_and_revokes_family(
        self, refresh_token_repo, registered_user, auth_config, monkeypatch
    ):
        """Simulates two concurrent /auth/refresh calls with the same token: both
        pass the initial used_at/revoked/expired checks, but only one can win
        the atomic mark_used update. The loser must be treated as reuse."""
        original = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        monkeypatch.setattr(refresh_token_repo, "mark_used", AsyncMock(return_value=False))

        with pytest.raises(RefreshTokenReuseDetected):
            await service.rotate_refresh_token(
                refresh_token_repo, original.refresh_token, config=auth_config, now=NOW
            )

        record = await refresh_token_repo.get_by_hash(_hash(original.refresh_token))
        assert record.revoked_at == NOW


class TestLogout:
    async def test_revokes_the_token_family(self, refresh_token_repo, registered_user, auth_config):
        pair = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )

        await service.logout(refresh_token_repo, pair.refresh_token, now=NOW)

        record = await refresh_token_repo.get_by_hash(_hash(pair.refresh_token))
        assert record.revoked_at == NOW

    async def test_is_a_no_op_for_unknown_token(self, refresh_token_repo):
        await service.logout(refresh_token_repo, "never-issued-token", now=NOW)

    async def test_calling_logout_twice_is_idempotent(
        self, refresh_token_repo, registered_user, auth_config
    ):
        pair = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )

        await service.logout(refresh_token_repo, pair.refresh_token, now=NOW)
        later = NOW + timedelta(minutes=5)
        await service.logout(refresh_token_repo, pair.refresh_token, now=later)

        record = await refresh_token_repo.get_by_hash(_hash(pair.refresh_token))
        assert record.revoked_at == NOW


@pytest.fixture
async def unverified_user(user_repo):
    return await service.register_user(user_repo, email="grace@example.com", password="s3cret-pw")


class TestConfirmEmail:
    async def test_marks_user_verified(
        self,
        email_verification_token_repo,
        user_repo,
        email_outbox_repo,
        unverified_user,
        auth_config,
    ):
        entry = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            unverified_user,
            config=auth_config,
            now=NOW,
        )

        confirmed = await service.confirm_email(
            email_verification_token_repo, user_repo, entry.token, now=NOW
        )

        assert confirmed.email_verified_at == NOW

    async def test_raises_for_unknown_token(self, email_verification_token_repo, user_repo):
        with pytest.raises(InvalidVerificationToken):
            await service.confirm_email(
                email_verification_token_repo, user_repo, "never-issued-token", now=NOW
            )

    async def test_raises_for_already_used_token(
        self,
        email_verification_token_repo,
        user_repo,
        email_outbox_repo,
        unverified_user,
        auth_config,
    ):
        entry = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            unverified_user,
            config=auth_config,
            now=NOW,
        )
        await service.confirm_email(email_verification_token_repo, user_repo, entry.token, now=NOW)

        with pytest.raises(InvalidVerificationToken):
            await service.confirm_email(
                email_verification_token_repo, user_repo, entry.token, now=NOW
            )

    async def test_raises_exactly_at_expiry_instant(
        self,
        email_verification_token_repo,
        user_repo,
        email_outbox_repo,
        unverified_user,
        auth_config,
    ):
        entry = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            unverified_user,
            config=auth_config,
            now=NOW,
        )
        exact_expiry = NOW + auth_config.EMAIL_VERIFICATION_TOKEN_EXP

        with pytest.raises(VerificationTokenExpired):
            await service.confirm_email(
                email_verification_token_repo, user_repo, entry.token, now=exact_expiry
            )

    async def test_expired_token_does_not_verify_user(
        self,
        email_verification_token_repo,
        user_repo,
        email_outbox_repo,
        unverified_user,
        auth_config,
    ):
        entry = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            unverified_user,
            config=auth_config,
            now=NOW,
        )
        after_expiry = NOW + auth_config.EMAIL_VERIFICATION_TOKEN_EXP + timedelta(seconds=1)

        with pytest.raises(VerificationTokenExpired):
            await service.confirm_email(
                email_verification_token_repo, user_repo, entry.token, now=after_expiry
            )

        user = await user_repo.get_by_id(unverified_user.id)
        assert user.email_verified_at is None

    async def test_losing_the_mark_used_race_raises_invalid(
        self,
        email_verification_token_repo,
        user_repo,
        email_outbox_repo,
        unverified_user,
        auth_config,
        monkeypatch,
    ):
        """simulates two concurrent /auth/confirm-email calls with the same
        token: both pass the initial used/expired checks, but only one can
        win the atomic mark_used update."""
        entry = await service.queue_verification_email(
            email_verification_token_repo,
            email_outbox_repo,
            unverified_user,
            config=auth_config,
            now=NOW,
        )
        monkeypatch.setattr(
            email_verification_token_repo, "mark_used", AsyncMock(return_value=False)
        )

        with pytest.raises(InvalidVerificationToken):
            await service.confirm_email(
                email_verification_token_repo, user_repo, entry.token, now=NOW
            )


class TestResendVerificationEmail:
    async def test_queues_new_token_for_known_unverified_user(
        self,
        email_verification_token_repo,
        user_repo,
        email_outbox_repo,
        unverified_user,
        auth_config,
    ):
        entry = await service.resend_verification_email(
            email_verification_token_repo,
            user_repo,
            email_outbox_repo,
            email="grace@example.com",
            config=auth_config,
            now=NOW,
        )

        assert entry is not None
        assert entry.email == "grace@example.com"

    async def test_is_a_no_op_for_unknown_email(
        self, email_verification_token_repo, user_repo, email_outbox_repo, auth_config
    ):
        entry = await service.resend_verification_email(
            email_verification_token_repo,
            user_repo,
            email_outbox_repo,
            email="nobody@example.com",
            config=auth_config,
            now=NOW,
        )

        assert entry is None

    async def test_is_a_no_op_for_already_verified_email(
        self,
        email_verification_token_repo,
        user_repo,
        email_outbox_repo,
        registered_user,
        auth_config,
    ):
        entry = await service.resend_verification_email(
            email_verification_token_repo,
            user_repo,
            email_outbox_repo,
            email=registered_user.email,
            config=auth_config,
            now=NOW,
        )

        assert entry is None

    async def test_normalizes_email_case(
        self,
        email_verification_token_repo,
        user_repo,
        email_outbox_repo,
        unverified_user,
        auth_config,
    ):
        entry = await service.resend_verification_email(
            email_verification_token_repo,
            user_repo,
            email_outbox_repo,
            email="Grace@Example.com",
            config=auth_config,
            now=NOW,
        )

        assert entry is not None


NEW_PASSWORD = "n3w-s3cret-pw"


class TestRequestPasswordReset:
    async def test_queues_email_to_the_users_address(
        self, password_reset_token_repo, user_repo, email_outbox_repo, registered_user, auth_config
    ):
        entry = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="ada@example.com",
            config=auth_config,
            now=NOW,
        )

        assert entry is not None
        assert entry.email == "ada@example.com"
        assert entry.user_id == registered_user.id

    async def test_stores_hashed_token_not_raw_value(
        self, password_reset_token_repo, user_repo, email_outbox_repo, registered_user, auth_config
    ):
        entry = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="ada@example.com",
            config=auth_config,
            now=NOW,
        )

        stored = await password_reset_token_repo.get_by_hash(_hash(entry.token))
        assert stored is not None
        assert stored.token_hash != entry.token

    async def test_sets_expiry_from_config(
        self, password_reset_token_repo, user_repo, email_outbox_repo, registered_user, auth_config
    ):
        entry = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="ada@example.com",
            config=auth_config,
            now=NOW,
        )

        stored = await password_reset_token_repo.get_by_hash(_hash(entry.token))
        assert stored.expires_at == NOW + auth_config.PASSWORD_RESET_TOKEN_EXP

    async def test_enqueues_a_password_reset_kind_email(
        self, password_reset_token_repo, user_repo, email_outbox_repo, registered_user, auth_config
    ):
        entry = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="ada@example.com",
            config=auth_config,
            now=NOW,
        )

        assert entry.kind == EmailKind.PASSWORD_RESET

    async def test_normalizes_email_case(
        self, password_reset_token_repo, user_repo, email_outbox_repo, registered_user, auth_config
    ):
        entry = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="  Ada@Example.com  ",
            config=auth_config,
            now=NOW,
        )

        assert entry is not None
        assert entry.email == "ada@example.com"

    async def test_returns_none_for_unknown_email_without_minting_a_token(
        self, password_reset_token_repo, user_repo, email_outbox_repo, auth_config
    ):
        """Unknown addresses must be indistinguishable from known ones to the caller."""
        entry = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="nobody@example.com",
            config=auth_config,
            now=NOW,
        )

        assert entry is None
        assert await password_reset_token_repo.get_by_hash(_hash("anything")) is None

    async def test_returns_none_for_unverified_user(
        self, password_reset_token_repo, user_repo, email_outbox_repo, unverified_user, auth_config
    ):
        """An unconfirmed address hasn't been proven to belong to the account yet."""
        entry = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="grace@example.com",
            config=auth_config,
            now=NOW,
        )

        assert entry is None

    async def test_second_request_issues_a_different_token(
        self, password_reset_token_repo, user_repo, email_outbox_repo, registered_user, auth_config
    ):
        first = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="ada@example.com",
            config=auth_config,
            now=NOW,
        )
        second = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="ada@example.com",
            config=auth_config,
            now=NOW + timedelta(minutes=1),
        )

        assert second.token != first.token


@pytest.fixture
async def reset_token(password_reset_token_repo, user_repo, email_outbox_repo, auth_config):
    """The raw reset token emailed to `registered_user`, as the reset step receives it."""

    async def _request(now=NOW):
        entry = await service.request_password_reset(
            password_reset_token_repo,
            user_repo,
            email_outbox_repo,
            email="ada@example.com",
            config=auth_config,
            now=now,
        )
        return entry.token

    return _request


class TestAssertResetTokenValid:
    async def test_returns_none_for_a_live_token_without_consuming_it(
        self, password_reset_token_repo, registered_user, reset_token
    ):
        token = await reset_token()

        assert (
            await service.assert_reset_token_valid(password_reset_token_repo, token, now=NOW)
            is None
        )

        stored = await password_reset_token_repo.get_by_hash(_hash(token))
        assert stored.used_at is None

    async def test_raises_invalid_for_unknown_token(self, password_reset_token_repo):
        with pytest.raises(InvalidPasswordResetToken):
            await service.assert_reset_token_valid(
                password_reset_token_repo, "never-issued", now=NOW
            )

    async def test_raises_expired_at_the_expiry_instant(
        self, password_reset_token_repo, registered_user, reset_token, auth_config
    ):
        token = await reset_token()

        with pytest.raises(PasswordResetTokenExpired):
            await service.assert_reset_token_valid(
                password_reset_token_repo,
                token,
                now=NOW + auth_config.PASSWORD_RESET_TOKEN_EXP,
            )


class TestResetPassword:
    async def test_new_password_authenticates(
        self, password_reset_token_repo, user_repo, refresh_token_repo, registered_user, reset_token
    ):
        token = await reset_token()

        await service.reset_password(
            password_reset_token_repo,
            user_repo,
            refresh_token_repo,
            token,
            new_password=NEW_PASSWORD,
            now=NOW,
        )

        user = await service.authenticate_user(
            user_repo, email="ada@example.com", password=NEW_PASSWORD
        )
        assert user.id == registered_user.id

    async def test_old_password_stops_working(
        self, password_reset_token_repo, user_repo, refresh_token_repo, registered_user, reset_token
    ):
        token = await reset_token()

        await service.reset_password(
            password_reset_token_repo,
            user_repo,
            refresh_token_repo,
            token,
            new_password=NEW_PASSWORD,
            now=NOW,
        )

        with pytest.raises(InvalidCredentials):
            await service.authenticate_user(
                user_repo, email="ada@example.com", password="s3cret-pw"
            )

    async def test_stores_argon2_hash_not_the_raw_password(
        self, password_reset_token_repo, user_repo, refresh_token_repo, registered_user, reset_token
    ):
        token = await reset_token()

        await service.reset_password(
            password_reset_token_repo,
            user_repo,
            refresh_token_repo,
            token,
            new_password=NEW_PASSWORD,
            now=NOW,
        )

        user = await user_repo.get_by_id(registered_user.id)
        assert user.password_hash != NEW_PASSWORD
        assert user.password_hash.startswith("$argon2id$")

    async def test_marks_the_token_used(
        self, password_reset_token_repo, user_repo, refresh_token_repo, registered_user, reset_token
    ):
        token = await reset_token()

        await service.reset_password(
            password_reset_token_repo,
            user_repo,
            refresh_token_repo,
            token,
            new_password=NEW_PASSWORD,
            now=NOW,
        )

        stored = await password_reset_token_repo.get_by_hash(_hash(token))
        assert stored.used_at == NOW

    async def test_reusing_a_spent_token_raises_invalid(
        self, password_reset_token_repo, user_repo, refresh_token_repo, registered_user, reset_token
    ):
        token = await reset_token()
        await service.reset_password(
            password_reset_token_repo,
            user_repo,
            refresh_token_repo,
            token,
            new_password=NEW_PASSWORD,
            now=NOW,
        )

        with pytest.raises(InvalidPasswordResetToken):
            await service.reset_password(
                password_reset_token_repo,
                user_repo,
                refresh_token_repo,
                token,
                new_password="third-password",
                now=NOW,
            )

    async def test_unknown_token_raises_invalid(
        self, password_reset_token_repo, user_repo, refresh_token_repo
    ):
        with pytest.raises(InvalidPasswordResetToken):
            await service.reset_password(
                password_reset_token_repo,
                user_repo,
                refresh_token_repo,
                "never-issued-token",
                new_password=NEW_PASSWORD,
                now=NOW,
            )

    async def test_raises_exactly_at_the_expiry_instant(
        self,
        password_reset_token_repo,
        user_repo,
        refresh_token_repo,
        registered_user,
        reset_token,
        auth_config,
    ):
        token = await reset_token()

        with pytest.raises(PasswordResetTokenExpired):
            await service.reset_password(
                password_reset_token_repo,
                user_repo,
                refresh_token_repo,
                token,
                new_password=NEW_PASSWORD,
                now=NOW + auth_config.PASSWORD_RESET_TOKEN_EXP,
            )

    async def test_expired_token_leaves_the_password_unchanged(
        self,
        password_reset_token_repo,
        user_repo,
        refresh_token_repo,
        registered_user,
        reset_token,
        auth_config,
    ):
        token = await reset_token()
        after_expiry = NOW + auth_config.PASSWORD_RESET_TOKEN_EXP + timedelta(seconds=1)

        with pytest.raises(PasswordResetTokenExpired):
            await service.reset_password(
                password_reset_token_repo,
                user_repo,
                refresh_token_repo,
                token,
                new_password=NEW_PASSWORD,
                now=after_expiry,
            )

        user = await service.authenticate_user(
            user_repo, email="ada@example.com", password="s3cret-pw"
        )
        assert user.id == registered_user.id

    async def test_losing_the_mark_used_race_raises_invalid_and_changes_nothing(
        self,
        password_reset_token_repo,
        user_repo,
        refresh_token_repo,
        registered_user,
        reset_token,
        monkeypatch,
    ):
        """Two concurrent resets with the same token both pass the used/expired
        checks, but only one wins the atomic mark_used update. The loser must
        not go on to write a password."""
        token = await reset_token()
        monkeypatch.setattr(password_reset_token_repo, "mark_used", AsyncMock(return_value=False))

        with pytest.raises(InvalidPasswordResetToken):
            await service.reset_password(
                password_reset_token_repo,
                user_repo,
                refresh_token_repo,
                token,
                new_password=NEW_PASSWORD,
                now=NOW,
            )

        user = await service.authenticate_user(
            user_repo, email="ada@example.com", password="s3cret-pw"
        )
        assert user.id == registered_user.id

    async def test_signs_out_every_existing_session_for_that_user(
        self,
        password_reset_token_repo,
        user_repo,
        refresh_token_repo,
        registered_user,
        reset_token,
        auth_config,
    ):
        phone = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        laptop = await service.issue_token_pair(
            refresh_token_repo, registered_user, config=auth_config, now=NOW
        )
        token = await reset_token()

        await service.reset_password(
            password_reset_token_repo,
            user_repo,
            refresh_token_repo,
            token,
            new_password=NEW_PASSWORD,
            now=NOW,
        )

        for pair in (phone, laptop):
            with pytest.raises(InvalidRefreshToken):
                await service.rotate_refresh_token(
                    refresh_token_repo, pair.refresh_token, config=auth_config, now=NOW
                )

    async def test_does_not_sign_out_other_users(
        self,
        password_reset_token_repo,
        user_repo,
        refresh_token_repo,
        registered_user,
        reset_token,
        auth_config,
    ):
        other = await service.register_user(
            user_repo, email="grace@example.com", password="s3cret-pw"
        )
        await user_repo.mark_email_verified(other.id, verified_at=NOW)
        other_session = await service.issue_token_pair(
            refresh_token_repo, other, config=auth_config, now=NOW
        )
        token = await reset_token()

        await service.reset_password(
            password_reset_token_repo,
            user_repo,
            refresh_token_repo,
            token,
            new_password=NEW_PASSWORD,
            now=NOW,
        )

        rotated = await service.rotate_refresh_token(
            refresh_token_repo, other_session.refresh_token, config=auth_config, now=NOW
        )
        assert rotated.refresh_token != other_session.refresh_token

    async def test_burns_any_other_outstanding_reset_token_for_that_user(
        self, password_reset_token_repo, user_repo, refresh_token_repo, registered_user, reset_token
    ):
        """Requesting twice then resetting once must not leave a second live
        token an attacker could redeem afterwards."""
        first = await reset_token()
        second = await reset_token(NOW + timedelta(minutes=1))

        await service.reset_password(
            password_reset_token_repo,
            user_repo,
            refresh_token_repo,
            second,
            new_password=NEW_PASSWORD,
            now=NOW + timedelta(minutes=2),
        )

        with pytest.raises(InvalidPasswordResetToken):
            await service.reset_password(
                password_reset_token_repo,
                user_repo,
                refresh_token_repo,
                first,
                new_password="third-password",
                now=NOW + timedelta(minutes=3),
            )
