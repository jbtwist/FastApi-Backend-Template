from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.mail.repository import SqlEmailOutboxRepository

DbDep = Annotated[AsyncSession, Depends(get_db)]


def get_email_outbox_repo(db: DbDep) -> SqlEmailOutboxRepository:
    return SqlEmailOutboxRepository(db)


EmailOutboxRepoDep = Annotated[SqlEmailOutboxRepository, Depends(get_email_outbox_repo)]
