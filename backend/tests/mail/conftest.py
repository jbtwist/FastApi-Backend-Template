import pytest

from tests.mail.fakes import FakeEmailSender


@pytest.fixture
def email_sender() -> FakeEmailSender:
    return FakeEmailSender()
