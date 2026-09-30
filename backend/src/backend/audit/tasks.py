"""Celery task keeping the security-event table from growing without bound."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from backend.audit.config import audit_settings
from backend.audit.repository import SqlSecurityEventRepository
from backend.audit.service import purge_expired_security_events
from backend.database import WorkerSessionFactory
from backend.log import correlation_id, new_correlation_id
from backend.mail.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _purge_one_batch() -> int:
    """Delete one committed batch of expired rows, returning how many went."""
    async with WorkerSessionFactory() as db, db.begin():
        security_event_repo = SqlSecurityEventRepository(db)
        return await purge_expired_security_events(
            security_event_repo,
            now=datetime.now(UTC),
            retention=timedelta(days=audit_settings.SECURITY_EVENT_RETENTION_DAYS),
            batch_size=audit_settings.SECURITY_EVENT_PURGE_BATCH_SIZE,
        )


async def _sweep_security_events() -> int:
    """Drain every expired row, one committed batch at a time.

    The loop is here rather than in the repository because each batch needs its
    own transaction. Holding one open across the whole purge would keep the dead
    tuples unreclaimable and stall vacuum on every other table too.
    """
    total = 0
    while (deleted := await _purge_one_batch()) > 0:
        total += deleted
    return total


@celery_app.task(name="backend.audit.tasks.sweep_security_events")
def sweep_security_events() -> None:
    """Celery beat task: delete security events past `SECURITY_EVENT_RETENTION_DAYS`."""
    correlation_id.set(new_correlation_id())
    deleted = asyncio.run(_sweep_security_events())
    logger.info("purged %s expired security events", deleted)
