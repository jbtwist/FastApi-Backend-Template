import pytest

from backend.audit.config import AuditConfig
from tests.audit.fakes import FakeSecurityEventRepository


@pytest.fixture
def security_event_repo() -> FakeSecurityEventRepository:
    return FakeSecurityEventRepository()


@pytest.fixture
def audit_config() -> AuditConfig:
    return AuditConfig(
        SECURITY_EVENT_RETENTION_DAYS=180,
        SECURITY_EVENT_SWEEP_INTERVAL_SECONDS=86400,
    )
