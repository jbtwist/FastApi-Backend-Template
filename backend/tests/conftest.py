import pytest

from tests.mail.fakes import FakeEmailOutboxRepository


@pytest.fixture
def email_outbox_repo() -> FakeEmailOutboxRepository:
    return FakeEmailOutboxRepository()
