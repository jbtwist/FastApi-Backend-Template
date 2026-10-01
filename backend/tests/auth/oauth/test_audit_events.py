"""The `audit_event` records each provider sign-in outcome leaves on `backend.audit`."""

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.auth import service as auth_service
from backend.auth.oauth import service
from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.exceptions import EmailLinkedToOtherProvider, ProviderEmailUnverified

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


def _events(records: list[logging.LogRecord]) -> list[str]:
    """Audit event names, leaving out the per-row `db_write` records."""
    return [record.event for record in records if record.event != "db_write"]


def _only(records: list[logging.LogRecord], event: str) -> logging.LogRecord:
    """The one record named `event`, which must come from the `oauth` audit logger."""
    [record] = [record for record in records if record.event == event]
    assert record.name == "backend.audit.oauth"
    return record


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
    async def _sign_in(identity: ProviderIdentity = IDENTITY):
        return await service.sign_in_with_provider(
            user_repo,
            identity_repo,
            refresh_token_repo,
            link_token_repo,
            email_outbox_repo,
            identity,
            auth_config=auth_config,
            oauth_config=oauth_config,
            now=NOW,
        )

    return _sign_in


@pytest.fixture
def confirm_link(link_token_repo, identity_repo):
    async def _confirm(raw_token: str):
        return await service.confirm_identity_link(
            link_token_repo, identity_repo, raw_token, now=NOW
        )

    return _confirm


@pytest.fixture
async def unverified_user(user_repo):
    return await auth_service.register_user(user_repo, email="ada@example.com", password=PASSWORD)


@pytest.fixture
async def verified_user(user_repo, unverified_user):
    await user_repo.mark_email_verified(unverified_user.id, verified_at=NOW - timedelta(days=1))
    return await user_repo.get_by_id(unverified_user.id)


async def _link(identity_repo, user, *, provider="fake", provider_subject="fake-subject-1"):
    return await identity_repo.create(
        user_id=user.id,
        provider=provider,
        provider_subject=provider_subject,
        email_at_link=user.email,
        is_private_relay=False,
        display_name=None,
    )


class TestSignIn:
    async def test_a_returning_identity_records_login_succeeded_with_method_oauth(
        self, sign_in, identity_repo, verified_user, captured_records
    ):
        await _link(identity_repo, verified_user)
        captured_records.clear()

        await sign_in()

        assert _events(captured_records) == ["login.succeeded"]
        assert _only(captured_records, "login.succeeded").audit_fields == {
            "user_id": verified_user.id,
            "method": "oauth",
            "provider": "fake",
        }

    async def test_a_new_account_records_registration_link_and_login(
        self, sign_in, captured_records
    ):
        result = await sign_in()

        assert _events(captured_records) == [
            "user.registered",
            "oauth.identity_linked",
            "login.succeeded",
        ]
        user_id = result.user.id
        assert _only(captured_records, "user.registered").audit_fields == {
            "user_id": user_id,
            "method": "oauth",
            "provider": "fake",
        }
        assert _only(captured_records, "oauth.identity_linked").audit_fields == {
            "user_id": user_id,
            "provider": "fake",
            "reason": "new_account",
        }

    async def test_claiming_an_unverified_account_records_the_takeover(
        self, sign_in, unverified_user, captured_records
    ):
        captured_records.clear()

        await sign_in()

        assert _events(captured_records) == [
            "sessions.revoked_all",
            "oauth.identity_linked",
            "login.succeeded",
        ]
        revoked_all = _only(captured_records, "sessions.revoked_all")
        assert revoked_all.levelno == logging.WARNING
        assert revoked_all.audit_fields == {
            "user_id": unverified_user.id,
            "reason": "oauth_account_claimed",
        }
        assert (
            _only(captured_records, "oauth.identity_linked").audit_fields["reason"]
            == "unverified_account_claimed"
        )

    async def test_a_verified_account_records_the_link_request(
        self, sign_in, verified_user, captured_records
    ):
        captured_records.clear()

        await sign_in()

        assert _events(captured_records) == ["oauth.link_requested"]
        assert _only(captured_records, "oauth.link_requested").audit_fields == {
            "user_id": verified_user.id,
            "provider": "fake",
        }

    async def test_an_account_with_another_provider_records_a_warning(
        self, sign_in, identity_repo, verified_user, captured_records
    ):
        await _link(identity_repo, verified_user, provider="second_fake", provider_subject="x")
        captured_records.clear()

        with pytest.raises(EmailLinkedToOtherProvider):
            await sign_in()

        record = _only(captured_records, "oauth.link_refused")
        assert record.levelno == logging.WARNING
        assert record.audit_fields == {
            "user_id": verified_user.id,
            "provider": "fake",
            "linked_provider": "second_fake",
        }

    async def test_an_unverified_provider_email_names_no_account(self, sign_in, captured_records):
        with pytest.raises(ProviderEmailUnverified):
            await sign_in(replace(IDENTITY, email_verified=False))

        assert _events(captured_records) == []


class TestConfirmIdentityLink:
    @pytest.fixture
    async def raw_link_token(self, sign_in, verified_user, captured_records) -> str:
        result = await sign_in()
        captured_records.clear()
        return result.outbox_entry.token

    async def test_confirming_records_the_link(
        self, confirm_link, verified_user, raw_link_token, captured_records
    ):
        await confirm_link(raw_link_token)

        assert _events(captured_records) == ["oauth.identity_linked"]
        assert _only(captured_records, "oauth.identity_linked").audit_fields == {
            "user_id": verified_user.id,
            "provider": "fake",
            "reason": "link_confirmed",
        }

    async def test_the_account_getting_another_provider_meanwhile_is_refused(
        self, confirm_link, identity_repo, verified_user, raw_link_token, captured_records
    ):
        await _link(identity_repo, verified_user, provider="second_fake", provider_subject="x")
        captured_records.clear()

        with pytest.raises(EmailLinkedToOtherProvider):
            await confirm_link(raw_link_token)

        assert _only(captured_records, "oauth.link_refused").audit_fields == {
            "user_id": verified_user.id,
            "provider": "fake",
            "linked_provider": "second_fake",
        }

    async def test_the_identity_linked_elsewhere_meanwhile_is_refused(
        self,
        confirm_link,
        user_repo,
        identity_repo,
        verified_user,
        raw_link_token,
        captured_records,
    ):
        other = await user_repo.create(email="other@example.com", password_hash=None)
        await _link(identity_repo, other)
        captured_records.clear()

        with pytest.raises(EmailLinkedToOtherProvider):
            await confirm_link(raw_link_token)

        assert _only(captured_records, "oauth.link_refused").audit_fields == {
            "user_id": verified_user.id,
            "provider": "fake",
            "linked_provider": "fake",
        }
