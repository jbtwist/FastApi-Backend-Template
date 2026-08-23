from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.auth import service
from backend.auth.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidRefreshToken,
    RefreshTokenExpired,
    RefreshTokenReuseDetected,
)
from backend.auth.security import hash_refresh_token as _hash

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def registered_user(user_repo):
    return await service.register_user(user_repo, email="ada@example.com", password="s3cret-pw")


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
            await service.authenticate_user(
                user_repo, email="ada@example.com", password="wrong-pw"
            )

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

        # the legitimately-rotated token must also be dead: whole family is burned
        with pytest.raises(InvalidRefreshToken):
            await service.rotate_refresh_token(
                refresh_token_repo, rotated.refresh_token, config=auth_config, now=NOW
            )

    async def test_reuse_detection_only_burns_that_family_not_other_sessions(
        self, refresh_token_repo, registered_user, auth_config
    ):
        # e.g. one browser session's token got stolen and replayed; a second,
        # legitimate session (different login/family) must be unaffected.
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

        # session_b's family was never touched by the reuse in family a
        rotated_b = await service.rotate_refresh_token(
            refresh_token_repo, session_b.refresh_token, config=auth_config, now=NOW
        )
        assert rotated_b.refresh_token != session_b.refresh_token
        # rotated_a (the legitimate rotation in family a) is dead too, per reuse policy
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

        # still unused/not rotated afterward
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
        # simulates two concurrent /auth/refresh calls with the same token: both
        # pass the initial used_at/revoked/expired checks, but only one can win
        # the atomic mark_used update. The loser must be treated as reuse.
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
    async def test_revokes_the_token_family(
        self, refresh_token_repo, registered_user, auth_config
    ):
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
        # first call's revocation timestamp wins; second call is a no-op
        assert record.revoked_at == NOW
