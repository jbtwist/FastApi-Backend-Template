"""Failures raised across the provider seam. None of them carries provider-supplied data."""


class ProviderNotConfigured(Exception):
    """The named provider has no adapter module, no `PROVIDER`, or incomplete settings.

    Rendered exactly like an unknown provider name, so a deployment never reveals
    which providers it has half set up.
    """


class ProviderAssertionInvalid(Exception):
    """A provider assertion failed verification: signature, issuer, audience, expiry or nonce.

    Always a refusal, never retried, and never carrying the assertion itself.
    """


class ProviderUnavailable(Exception):
    """The provider, or its signing keys, could not be reached. Retryable."""


class ProviderEmailUnverified(Exception):
    """The provider did not vouch for the person's email address, or supplied none.

    Separate from `ProviderAssertionInvalid` because it is the one refusal with a
    next step: register with the address and confirm it.
    """
