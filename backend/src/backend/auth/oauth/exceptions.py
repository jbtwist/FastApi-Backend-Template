"""Failures raised across the provider seam. None of them carries provider-supplied data."""


class ProviderNotConfigured(Exception):
    """The named provider has no adapter module, no `PROVIDER`, or incomplete settings.

    Rendered exactly like an unknown name, so a deployment never reveals which
    providers it has half set up.
    """


class ProviderAssertionInvalid(Exception):
    """A provider assertion failed verification: signature, issuer, audience, expiry or nonce.

    Never retried, and never carries the assertion itself.
    """


class ProviderUnavailable(Exception):
    """The provider, or its signing keys, could not be reached. Retryable."""


class InvalidOAuthState(Exception):
    """The `state` is unknown, already spent, expired, or was started for another provider."""


class EmailLinkedToOtherProvider(Exception):
    """The account with this email already has a provider identity; an account holds at most one.

    `linked_provider` is a configured adapter name, never provider-supplied data,
    so the client can name the provider to use instead.
    """

    def __init__(self, linked_provider: str) -> None:
        super().__init__(linked_provider)
        self.linked_provider = linked_provider


class InvalidOAuthLinkToken(Exception):
    """The `oauth_link_token` is unknown, already used, or lost the race to be used."""


class OAuthLinkTokenExpired(Exception):
    """The `oauth_link_token` exists but is at or past its `expires_at`."""


class ProviderEmailUnverified(Exception):
    """The provider did not vouch for the person's email address, or supplied none.

    Separate from `ProviderAssertionInvalid` because it is the one refusal with a
    next step: register with the address and confirm it.
    """
