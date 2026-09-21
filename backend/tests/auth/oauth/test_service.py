from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from backend.auth import service as auth_service
from backend.auth.exceptions import InvalidCredentials
from backend.auth.oauth import service
from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.exceptions import (
    EmailLinkedToOtherProvider,
    InvalidOAuthLinkToken,
    InvalidOAuthState,
    OAuthLinkTokenExpired,
    ProviderEmailUnverified,
)
from backend.auth.security import hash_opaque_token
from backend.mail.models import EmailKind

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "s3cret-pw-long-enough"

IDENTITY = ProviderIdentity(
    provider="fake",
    subject="fake-subject-1",
    email="ada@example.com",
    email_verified=True,
    is_private_relay=False,
    display_name="Ada",
)


def _duplicate_key() -> IntegrityError:
    return IntegrityError("INSERT", {}, Exception("duplicate key"))


@pytest.fixture
def sign_in(
    user_repo,
    identity_repo,
    refresh_token_repo,
    link_token_repo,
    email_outbox_repo,
    auth_config,
    oauth_config,
):
    """`sign_in_with_provider` over this test's fakes; only the identity and the time vary."""

    async def _sign_in(identity: ProviderIdentity = IDENTITY, *, now: datetime = NOW):
        return await service.sign_in_with_provider(
            user_repo,
            identity_repo,
            refresh_token_repo,
            link_token_repo,
            email_outbox_repo,
            identity,
            auth_config=auth_config,
            oauth_config=oauth_config,
            now=now,
        )

    return _sign_in


@pytest.fixture
def confirm_link(link_token_repo, identity_repo):
    async def _confirm(raw_token: str, *, now: datetime = NOW):
        return await service.confirm_identity_link(
            link_token_repo, identity_repo, raw_token, now=now
        )

    return _confirm


@pytest.fixture
async def verified_user(user_repo):
    user = await auth_service.register_user(user_repo, email="ada@example.com", password=PASSWORD)
    await user_repo.mark_email_verified(user.id, verified_at=NOW - timedelta(days=1))
    return user


@pytest.fixture
async def unverified_user(user_repo):
    return await auth_service.register_user(user_repo, email="ada@example.com", password=PASSWORD)


async def _link(identity_repo, user, *, provider="fake", provider_subject="fake-subject-1"):
    return await identity_repo.create(
        user_id=user.id,
        provider=provider,
        provider_subject=provider_subject,
        email_at_link=user.email,
        is_private_relay=False,
        display_name=None,
    )


async def _session_is_live(refresh_token_repo, result) -> bool:
    record = await refresh_token_repo.get_by_hash(hash_opaque_token(result.pair.refresh_token))
    return record is not None and record.revoked_at is None


class TestSafeRedirectTarget:
    @pytest.mark.parametrize("target", ["/", "/(app)", "/tasks/42", "/tasks?filter=today"])
    def test_keeps_an_app_relative_path(self, target):
        assert service.safe_redirect_target(target) == target

    @pytest.mark.parametrize(
        "target",
        [
            None,
            "",
            "tasks",
            "//evil.example",
            "//evil.example/path",
            "/\\evil.example",
            "https://evil.example/",
            "javascript:alert(1)",
            "/tasks\r\nSet-Cookie: x=1",
            " /tasks",
        ],
    )
    def test_falls_back_to_the_root_for_anything_else(self, target):
        assert service.safe_redirect_target(target) == "/"


class TestStartSignIn:
    async def test_stores_the_attempt_under_the_returned_state(self, state_store, oauth_config):
        state, attempt = await service.start_sign_in(
            state_store, provider="fake", redirect_target="/(app)", config=oauth_config
        )

        assert state_store.attempts[state] == attempt
        assert attempt.provider == "fake"
        assert attempt.redirect_target == "/(app)"

    async def test_the_attempt_lives_for_the_configured_state_ttl(self, state_store, oauth_config):
        state, _ = await service.start_sign_in(
            state_store, provider="fake", redirect_target=None, config=oauth_config
        )

        assert state_store.ttls[state] == oauth_config.OAUTH_STATE_TTL

    async def test_state_and_nonce_are_distinct_unguessable_values(self, state_store, oauth_config):
        state, attempt = await service.start_sign_in(
            state_store, provider="fake", redirect_target=None, config=oauth_config
        )

        assert state != attempt.nonce
        assert len(state) >= 32
        assert len(attempt.nonce) >= 32

    async def test_every_attempt_gets_fresh_values(self, state_store, oauth_config):
        first_state, first = await service.start_sign_in(
            state_store, provider="fake", redirect_target=None, config=oauth_config
        )
        second_state, second = await service.start_sign_in(
            state_store, provider="fake", redirect_target=None, config=oauth_config
        )

        assert first_state != second_state
        assert first.nonce != second.nonce

    async def test_an_unsafe_redirect_target_is_stored_as_the_root(self, state_store, oauth_config):
        _, attempt = await service.start_sign_in(
            state_store,
            provider="fake",
            redirect_target="https://evil.example/",
            config=oauth_config,
        )

        assert attempt.redirect_target == "/"


class TestConsumeSignInAttempt:
    @pytest.fixture
    async def started(self, state_store, oauth_config):
        return await service.start_sign_in(
            state_store, provider="fake", redirect_target="/(app)", config=oauth_config
        )

    async def test_returns_the_stored_attempt(self, state_store, started):
        state, attempt = started

        assert await service.consume_sign_in_attempt(state_store, state, provider="fake") == (
            attempt
        )

    async def test_an_attempt_can_be_consumed_only_once(self, state_store, started):
        state, _ = started
        await service.consume_sign_in_attempt(state_store, state, provider="fake")

        with pytest.raises(InvalidOAuthState):
            await service.consume_sign_in_attempt(state_store, state, provider="fake")

    async def test_refuses_an_unknown_state(self, state_store):
        with pytest.raises(InvalidOAuthState):
            await service.consume_sign_in_attempt(state_store, "never-issued", provider="fake")

    async def test_refuses_an_expired_attempt(self, state_store, started):
        state, _ = started
        state_store.expire(state)

        with pytest.raises(InvalidOAuthState):
            await service.consume_sign_in_attempt(state_store, state, provider="fake")

    async def test_refuses_and_spends_an_attempt_presented_for_another_provider(
        self, state_store, started
    ):
        state, _ = started

        with pytest.raises(InvalidOAuthState):
            await service.consume_sign_in_attempt(state_store, state, provider="second_fake")
        with pytest.raises(InvalidOAuthState):
            await service.consume_sign_in_attempt(state_store, state, provider="fake")


class TestReturningIdentity:
    async def test_signs_in_as_the_linked_user(
        self, sign_in, identity_repo, refresh_token_repo, verified_user
    ):
        await _link(identity_repo, verified_user)

        result = await sign_in()

        assert isinstance(result, service.SignedIn)
        assert result.user.id == verified_user.id
        assert await _session_is_live(refresh_token_repo, result)

    async def test_records_the_sign_in_time(self, sign_in, identity_repo, verified_user):
        link = await _link(identity_repo, verified_user)

        await sign_in()

        assert link.last_authenticated_at == NOW

    @pytest.mark.parametrize(
        "changes",
        [
            {"email": "someone-else@example.com"},
            {"email": None, "email_verified": False},
            {"email_verified": False},
        ],
    )
    async def test_ignores_whatever_the_email_now_says(
        self, sign_in, identity_repo, verified_user, changes
    ):
        await _link(identity_repo, verified_user)

        result = await sign_in(replace(IDENTITY, **changes))

        assert isinstance(result, service.SignedIn)
        assert result.user.id == verified_user.id


class TestUnverifiedProviderEmail:
    @pytest.mark.parametrize(
        "changes", [{"email": None, "email_verified": False}, {"email_verified": False}]
    )
    async def test_is_refused_without_creating_an_account(self, sign_in, user_repo, changes):
        with pytest.raises(ProviderEmailUnverified):
            await sign_in(replace(IDENTITY, **changes))

        assert await user_repo.get_by_email("ada@example.com") is None

    async def test_matching_an_existing_account_is_still_refused_and_changes_nothing(
        self, sign_in, identity_repo, link_token_repo, email_outbox_repo, verified_user
    ):
        with pytest.raises(ProviderEmailUnverified):
            await sign_in(replace(IDENTITY, email_verified=False))

        assert await identity_repo.get_by_user_id(verified_user.id) is None
        assert link_token_repo.all() == []
        assert await email_outbox_repo.list_stale_pending(older_than=NOW) == []

    async def test_cannot_take_over_an_unverified_account(
        self, sign_in, user_repo, unverified_user
    ):
        with pytest.raises(ProviderEmailUnverified):
            await sign_in(replace(IDENTITY, email_verified=False))

        user = await user_repo.get_by_id(unverified_user.id)
        assert user.password_hash is not None
        assert user.email_verified_at is None


class TestNewAccount:
    async def test_creates_a_verified_account_with_no_password(self, sign_in, user_repo):
        await sign_in()

        user = await user_repo.get_by_email("ada@example.com")
        assert user is not None
        assert user.password_hash is None
        assert user.email_verified_at == NOW

    async def test_normalises_the_email_like_registration_does(self, sign_in, user_repo):
        await sign_in(replace(IDENTITY, email="  Ada@Example.COM "))

        assert await user_repo.get_by_email("ada@example.com") is not None

    async def test_links_the_identity_to_the_new_account(self, sign_in, identity_repo):
        result = await sign_in()

        link = await identity_repo.get_by_provider_subject("fake", "fake-subject-1")
        assert link.user_id == result.user.id
        assert link.email_at_link == "ada@example.com"
        assert link.display_name == "Ada"
        assert link.is_private_relay is False

    async def test_signs_in(self, sign_in, refresh_token_repo):
        result = await sign_in()

        assert isinstance(result, service.SignedIn)
        assert await _session_is_live(refresh_token_repo, result)

    async def test_the_new_account_cannot_sign_in_with_a_password(self, sign_in, user_repo):
        await sign_in()

        with pytest.raises(InvalidCredentials):
            await auth_service.authenticate_user(user_repo, email="ada@example.com", password="")

    async def test_a_concurrent_first_sign_in_resolves_to_the_account_it_created(
        self, sign_in, user_repo, identity_repo, monkeypatch
    ):
        """Another request creates the account and link between our lookup and our insert."""
        create_user = user_repo.create

        async def racing_create(*, email: str, password_hash: str | None):
            winner = await create_user(email=email, password_hash=None)
            await _link(identity_repo, winner)
            raise _duplicate_key()

        monkeypatch.setattr(user_repo, "create", racing_create)

        result = await sign_in()

        assert isinstance(result, service.SignedIn)
        assert result.user.id == (await user_repo.get_by_email("ada@example.com")).id

    async def test_retries_a_race_only_once(self, sign_in, user_repo, monkeypatch):
        async def always_conflicting_create(*, email: str, password_hash: str | None):
            raise _duplicate_key()

        monkeypatch.setattr(user_repo, "create", always_conflicting_create)

        with pytest.raises(IntegrityError):
            await sign_in()


class TestAccountAlreadyLinked:
    async def test_linked_to_another_provider_is_refused_naming_that_provider(
        self, sign_in, identity_repo, verified_user
    ):
        await _link(identity_repo, verified_user, provider="second_fake", provider_subject="x")

        with pytest.raises(EmailLinkedToOtherProvider) as caught:
            await sign_in()

        assert caught.value.linked_provider == "second_fake"

    async def test_linked_to_another_identity_at_the_same_provider_is_refused(
        self, sign_in, identity_repo, verified_user
    ):
        await _link(identity_repo, verified_user, provider="fake", provider_subject="other")

        with pytest.raises(EmailLinkedToOtherProvider) as caught:
            await sign_in()

        assert caught.value.linked_provider == "fake"

    async def test_matches_the_account_whatever_the_email_case(
        self, sign_in, identity_repo, verified_user
    ):
        await _link(identity_repo, verified_user, provider="second_fake", provider_subject="x")

        with pytest.raises(EmailLinkedToOtherProvider):
            await sign_in(replace(IDENTITY, email="ADA@example.com"))

    async def test_neither_signs_in_nor_offers_a_link(
        self, sign_in, identity_repo, link_token_repo, email_outbox_repo, verified_user
    ):
        await _link(identity_repo, verified_user, provider="second_fake", provider_subject="x")

        with pytest.raises(EmailLinkedToOtherProvider):
            await sign_in()

        assert await identity_repo.get_by_provider_subject("fake", "fake-subject-1") is None
        assert link_token_repo.all() == []
        assert await email_outbox_repo.list_stale_pending(older_than=NOW) == []


class TestUnverifiedAccountTakeover:
    async def test_signs_in_as_the_existing_account(
        self, sign_in, refresh_token_repo, unverified_user
    ):
        result = await sign_in()

        assert isinstance(result, service.SignedIn)
        assert result.user.id == unverified_user.id
        assert await _session_is_live(refresh_token_repo, result)

    async def test_marks_the_address_verified_and_links_the_identity(
        self, sign_in, user_repo, identity_repo, unverified_user
    ):
        await sign_in()

        assert (await user_repo.get_by_id(unverified_user.id)).email_verified_at == NOW
        link = await identity_repo.get_by_user_id(unverified_user.id)
        assert (link.provider, link.provider_subject) == ("fake", "fake-subject-1")

    async def test_the_password_set_at_registration_stops_working(
        self, sign_in, user_repo, unverified_user
    ):
        await sign_in()

        assert (await user_repo.get_by_id(unverified_user.id)).password_hash is None
        with pytest.raises(InvalidCredentials):
            await auth_service.authenticate_user(
                user_repo, email="ada@example.com", password=PASSWORD
            )

    async def test_revokes_every_earlier_session_but_keeps_the_new_one(
        self, sign_in, refresh_token_repo, unverified_user, auth_config
    ):
        earlier = await auth_service.issue_token_pair(
            refresh_token_repo, unverified_user, config=auth_config, now=NOW
        )

        result = await sign_in()

        earlier_record = await refresh_token_repo.get_by_hash(
            hash_opaque_token(earlier.refresh_token)
        )
        assert earlier_record.revoked_at == NOW
        assert await _session_is_live(refresh_token_repo, result)


class TestLinkOffer:
    async def test_a_verified_account_with_no_provider_gets_a_pending_link(
        self, sign_in, identity_repo, verified_user
    ):
        result = await sign_in()

        assert isinstance(result, service.LinkPending)
        assert await identity_repo.get_by_user_id(verified_user.id) is None

    async def test_queues_the_link_email_to_the_account_address(self, sign_in, verified_user):
        result = await sign_in(replace(IDENTITY, email="ADA@example.com"))

        entry = result.outbox_entry
        assert entry.kind == EmailKind.OAUTH_LINK
        assert entry.user_id == verified_user.id
        assert entry.email == verified_user.email

    async def test_the_emailed_token_freezes_the_verified_identity(
        self, sign_in, link_token_repo, verified_user
    ):
        identity = replace(IDENTITY, is_private_relay=True, display_name="A. L.")

        result = await sign_in(identity)

        record = await link_token_repo.get_by_hash(hash_opaque_token(result.outbox_entry.token))
        assert record.user_id == verified_user.id
        assert record.provider == "fake"
        assert record.provider_subject == "fake-subject-1"
        assert record.email_at_link == "ada@example.com"
        assert record.is_private_relay is True
        assert record.display_name == "A. L."
        assert record.used_at is None

    async def test_the_token_expires_after_the_configured_lifetime(
        self, sign_in, link_token_repo, oauth_config, verified_user
    ):
        result = await sign_in()

        record = await link_token_repo.get_by_hash(hash_opaque_token(result.outbox_entry.token))
        assert record.expires_at == NOW + oauth_config.OAUTH_LINK_TOKEN_EXP

    async def test_a_new_offer_invalidates_the_previous_one(
        self, sign_in, link_token_repo, verified_user
    ):
        first = await sign_in()
        later = NOW + timedelta(minutes=1)

        second = await sign_in(now=later)

        first_record = await link_token_repo.get_by_hash(
            hash_opaque_token(first.outbox_entry.token)
        )
        second_record = await link_token_repo.get_by_hash(
            hash_opaque_token(second.outbox_entry.token)
        )
        assert first_record.used_at == later
        assert second_record.used_at is None

    async def test_leaves_the_account_and_its_password_alone(
        self, sign_in, user_repo, verified_user
    ):
        password_hash = verified_user.password_hash

        await sign_in()

        await auth_service.authenticate_user(user_repo, email="ada@example.com", password=PASSWORD)
        assert (await user_repo.get_by_id(verified_user.id)).password_hash == password_hash


class TestConfirmIdentityLink:
    @pytest.fixture
    async def raw_link_token(self, sign_in, verified_user) -> str:
        result = await sign_in()
        return result.outbox_entry.token

    async def test_links_the_frozen_identity_to_the_account(
        self, confirm_link, identity_repo, verified_user, raw_link_token
    ):
        await confirm_link(raw_link_token)

        link = await identity_repo.get_by_user_id(verified_user.id)
        assert (link.provider, link.provider_subject) == ("fake", "fake-subject-1")
        assert link.email_at_link == "ada@example.com"
        assert link.display_name == "Ada"

    async def test_after_confirming_the_provider_signs_in_to_the_account(
        self, sign_in, confirm_link, verified_user, raw_link_token
    ):
        await confirm_link(raw_link_token)

        result = await sign_in()

        assert isinstance(result, service.SignedIn)
        assert result.user.id == verified_user.id

    async def test_a_token_can_be_redeemed_only_once(self, confirm_link, raw_link_token):
        await confirm_link(raw_link_token)

        with pytest.raises(InvalidOAuthLinkToken):
            await confirm_link(raw_link_token)

    async def test_refuses_an_unknown_token(self, confirm_link, raw_link_token):
        with pytest.raises(InvalidOAuthLinkToken):
            await confirm_link("not-a-real-token")

    async def test_refuses_an_expired_token_without_linking(
        self, confirm_link, identity_repo, oauth_config, verified_user, raw_link_token
    ):
        with pytest.raises(OAuthLinkTokenExpired):
            await confirm_link(raw_link_token, now=NOW + oauth_config.OAUTH_LINK_TOKEN_EXP)

        assert await identity_repo.get_by_user_id(verified_user.id) is None

    async def test_refuses_a_token_superseded_by_a_newer_offer(
        self, sign_in, confirm_link, raw_link_token
    ):
        await sign_in(now=NOW + timedelta(minutes=1))

        with pytest.raises(InvalidOAuthLinkToken):
            await confirm_link(raw_link_token, now=NOW + timedelta(minutes=2))

    async def test_refuses_when_the_account_got_a_provider_meanwhile(
        self, confirm_link, identity_repo, verified_user, raw_link_token
    ):
        await _link(identity_repo, verified_user, provider="second_fake", provider_subject="x")

        with pytest.raises(EmailLinkedToOtherProvider) as caught:
            await confirm_link(raw_link_token)

        assert caught.value.linked_provider == "second_fake"

    async def test_refuses_when_the_identity_was_linked_to_another_account_meanwhile(
        self, confirm_link, user_repo, identity_repo, verified_user, raw_link_token
    ):
        other = await user_repo.create(email="other@example.com", password_hash=None)
        await _link(identity_repo, other)

        with pytest.raises(EmailLinkedToOtherProvider):
            await confirm_link(raw_link_token)

        assert await identity_repo.get_by_user_id(verified_user.id) is None

    async def test_a_link_insert_race_is_refused_not_raised_raw(
        self, confirm_link, identity_repo, raw_link_token, monkeypatch
    ):
        async def racing_create(**_):
            raise _duplicate_key()

        monkeypatch.setattr(identity_repo, "create", racing_create)

        with pytest.raises(EmailLinkedToOtherProvider):
            await confirm_link(raw_link_token)
